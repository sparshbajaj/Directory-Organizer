package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/sparshbajaj/directory-organizer/internal/aiclient"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/spf13/cobra"
)

var clientCmd = &cobra.Command{
	Use:   "client",
	Short: "Run VaultSort in lightweight remote client mode",
	Long:  `Runs a lightweight client that watches local directories and delegates AI organization to a remote VaultSort daemon server.`,
	RunE:  runClient,
}

func init() {
	rootCmd.AddCommand(clientCmd)
}

func runClient(cmd *cobra.Command, args []string) error {
	cfg, err := config.LoadFromEnv()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	if cfg.ServerURL == "" {
		return fmt.Errorf("VAULTSORT_SERVER_URL is required in client mode")
	}
	if len(cfg.WatchDirs) == 0 {
		return fmt.Errorf("VAULTSORT_DIRS is required")
	}

	// Ensure directories exist
	for _, dir := range cfg.WatchDirs {
		os.MkdirAll(dir, 0755)
	}

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return fmt.Errorf("failed to create watcher: %w", err)
	}
	defer watcher.Close()

	for _, d := range cfg.WatchDirs {
		if err := watcher.Add(d); err != nil {
			logger.Errorf("Failed to watch %s: %v", d, err)
		} else {
			logger.Infof("Client watching %s", d)
		}
	}

	// 1. Let the dashboard know a client connected
	emitRemoteEvent(cfg, events.Event{
		Type:   events.EventSystemStart,
		Source: "Windows Client",
		Detail: fmt.Sprintf("Remote client connected and watching %d directories", len(cfg.WatchDirs)),
	})

	// 2. Process existing files in the background (sequentially to avoid hitting API rate limits)
	go func() {
		for _, d := range cfg.WatchDirs {
			entries, _ := os.ReadDir(d)
			for _, entry := range entries {
				if !entry.IsDir() {
					handleRemoteFile(filepath.Join(d, entry.Name()), cfg)
				}
			}
		}
	}()

	// Print startup banner
	fmt.Println("╔══════════════════════════════════════════════════╗")
	fmt.Println("║          🚀 VaultSort Remote Client             ║")
	fmt.Printf( "║  Server:    %-37s ║\n", cfg.ServerURL)
	fmt.Printf( "║  Dirs:      %-37d ║\n", len(cfg.WatchDirs))
	fmt.Println("╚══════════════════════════════════════════════════╝")

	stopCh := make(chan struct{})
	go func() {
		for {
			select {
			case event, ok := <-watcher.Events:
				if !ok {
					return
				}
				if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
					go handleRemoteFile(event.Name, cfg)
				}
			case err, ok := <-watcher.Errors:
				if ok {
					logger.Errorf("watcher error: %v", err)
				}
			case <-stopCh:
				return
			}
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	logger.Info("Stopping client...")
	close(stopCh)
	return nil
}

func emitRemoteEvent(cfg *config.Settings, evt events.Event) {
	evt.Timestamp = time.Now()
	b, _ := json.Marshal(evt)
	http.Post(cfg.ServerURL+"/api/event", "application/json", bytes.NewBuffer(b))
}

func handleRemoteFile(path string, cfg *config.Settings) {
	// Wait a moment for file write to complete
	time.Sleep(2 * time.Second)

	info, err := os.Stat(path)
	if err != nil || info.IsDir() {
		return
	}
	originalName := filepath.Base(path)
	dir := filepath.Dir(path)

	emitRemoteEvent(cfg, events.Event{
		Type:     events.EventFileProcessing,
		Source:   dir,
		Detail:   fmt.Sprintf("[Remote] Processing %s", originalName),
		Metadata: map[string]string{"path": path},
	})

	// 1. Upload to server for analysis
	file, err := os.Open(path)
	if err != nil {
		logger.Errorf("failed to open file %s: %v", path, err)
		return
	}
	defer file.Close()

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	part, err := writer.CreateFormFile("file", originalName)
	if err == nil {
		io.Copy(part, file)
	}
	writer.Close()

	req, err := http.NewRequest("POST", cfg.ServerURL+"/api/analyze", body)
	if err != nil {
		return
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{Timeout: 3 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		logger.Errorf("server request failed: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		logger.Errorf("server error: %s", string(b))
		return
	}

	var aiRes aiclient.AIResult
	if err := json.NewDecoder(resp.Body).Decode(&aiRes); err != nil {
		logger.Errorf("decode ai result: %v", err)
		return
	}

	if aiRes.NewName == "" {
		return
	}

	// 2. Rename file locally
	ext := filepath.Ext(path)
	dest := filepath.Join(dir, aiRes.NewName+ext)

	if err := os.Rename(path, dest); err != nil {
		logger.Errorf("remote rename failed %s->%s: %v", path, dest, err)
		emitRemoteEvent(cfg, events.Event{
			Type:     events.EventFileError,
			Source:   dir,
			Detail:   fmt.Sprintf("[Remote] Rename failed: %s -> %s", originalName, aiRes.NewName+ext),
			Metadata: map[string]string{"error": err.Error()},
		})
		return
	}

	logger.Infof("Remote renamed %s -> %s", originalName, dest)
	
	// 3. Emit success event to server
	emitRemoteEvent(cfg, events.Event{
		Type:   events.EventFileMoved,
		Source: dir,
		Detail: fmt.Sprintf("[Remote] %s -> %s", originalName, aiRes.NewName+ext),
		Metadata: map[string]string{
			"original_path": path,
			"new_path":      dest,
			"new_name":      aiRes.NewName + ext,
			"original_name": originalName,
		},
	})
}
