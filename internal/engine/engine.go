// internal/engine/engine.go
package engine

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/sparshbajaj/directory-organizer/internal/aiclient"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	_ "modernc.org/sqlite"
)

type Engine struct {
	db        *sql.DB
	cfg       *config.Settings
	aiClient  *aiclient.Client
	watcher   *fsnotify.Watcher
	workQueue chan string
	stopCh    chan struct{}
	bus       *events.Bus
}

// NewEngine creates a new Engine instance, initializing DB and AI client.
func NewEngine(cfg *config.Settings) (*Engine, error) {
	// Ensure DB directory exists
	if err := os.MkdirAll(filepath.Dir(cfg.DBPath), 0755); err != nil {
		return nil, fmt.Errorf("mkdir db dir: %w", err)
	}
	// Ensure Watch directory exists
	if err := os.MkdirAll(cfg.WatchDir, 0755); err != nil {
		return nil, fmt.Errorf("mkdir watch dir: %w", err)
	}
	db, err := sql.Open("sqlite", cfg.DBPath)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}
	// Initialise schema
	schema := `
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        original_name TEXT,
        size INTEGER,
        mod_time INTEGER,
        metadata TEXT,
        context TEXT
    );`
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("init schema: %w", err)
	}
	// Initialise AI client (placeholder config)
	ai, err := aiclient.New(cfg)
	if err != nil {
		return nil, fmt.Errorf("ai client: %w", err)
	}
	eng := &Engine{
		db:        db,
		cfg:       cfg,
		aiClient:  ai,
		workQueue: make(chan string, 100),
		stopCh:    make(chan struct{}),
	}

	// Start 3 concurrent workers for renaming
	for i := 0; i < 3; i++ {
		go eng.worker()
	}

	return eng, nil
}

// SetBus attaches an event bus to the engine for emitting file processing events.
func (e *Engine) SetBus(bus *events.Bus) {
	e.bus = bus
}

// AIClient returns the initialized AI client.
func (e *Engine) AIClient() *aiclient.Client {
	return e.aiClient
}

// ScanDirectory walks the watch directory and stores file metadata.
func (e *Engine) ScanDirectory() error {
	logger.Infof("Scanning directory %s", e.cfg.WatchDir)
	return filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			logger.Errorf("walk error: %v", err)
			return err
		}
		if info.IsDir() {
			return nil
		}
		return e.upsertFile(p, info.Name(), info.Size(), info.ModTime(), "", "")
	})
}

func (e *Engine) upsertFile(path string, originalName string, size int64, modTime time.Time, metadata string, context string) error {
	stmt := `INSERT INTO files (path, original_name, size, mod_time, metadata, context) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET original_name=excluded.original_name, size=excluded.size, mod_time=excluded.mod_time, metadata=excluded.metadata, context=excluded.context;`
	_, err := e.db.Exec(stmt, path, originalName, size, modTime.Unix(), metadata, context)
	if err != nil {
		logger.Errorf("upsert %s: %v", path, err)
	}
	return err
}

// RegisterWatcher sets up a filesystem watcher that enqueues changed files.
func (e *Engine) RegisterWatcher() error {
	if e.watcher != nil {
		e.watcher.Close()
	}
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	e.watcher = w
	go e.watchLoop()
	return filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return w.Add(p)
		}
		return nil
	})
}

// OrganizeDirectory queues all existing files in the directory for processing
func (e *Engine) OrganizeDirectory() error {
	logger.Infof("Queuing directory %s for organization", e.cfg.WatchDir)
	go func() {
		count := 0
		filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if !info.IsDir() {
				// Blocking send ensures we don't drop files if queue fills up
				e.workQueue <- p
				count++
			}
			return nil
		})
		logger.Infof("Successfully queued %d files for organization.", count)
	}()
	return nil
}

func (e *Engine) watchLoop() {
	w := e.watcher // capture locally to avoid race on reassignment
	defer w.Close()
	for {
		select {
		case event, ok := <-w.Events:
			if !ok {
				return
			}
			if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
				e.Enqueue(event.Name)
			}
		case err, ok := <-w.Errors:
			if ok {
				logger.Errorf("watcher error: %v", err)
			}
		}
	}
}

func (e *Engine) Enqueue(path string) {
	select {
	case e.workQueue <- path:
		logger.Infof("Enqueued %s", path)
	default:
		logger.Errorf("Queue full, dropping event for %s", path)
	}
}

func (e *Engine) worker() {
	for {
		select {
		case <-e.stopCh:
			return
		case path := <-e.workQueue:
			e.handleFile(path)
		}
	}
}

func (e *Engine) handleFile(path string) {
	// Emit processing event
	if e.bus != nil {
		e.bus.Emit(events.Event{
			Type:     events.EventFileProcessing,
			Source:   filepath.Dir(path),
			Detail:   fmt.Sprintf("Processing %s", filepath.Base(path)),
			Metadata: map[string]string{"path": path},
		})
	}

	// Call AI to get a new name, metadata, and context
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute*2) // longer timeout for CLI
	defer cancel()

	res, err := e.aiClient.Analyze(ctx, path)
	if err != nil {
		logger.Errorf("AI analyze error for %s: %v", path, err)
		if e.bus != nil {
			e.bus.Emit(events.Event{
				Type:     events.EventFileError,
				Source:   filepath.Dir(path),
				Detail:   fmt.Sprintf("AI error for %s: %v", filepath.Base(path), err),
				Metadata: map[string]string{"path": path, "error": err.Error()},
			})
		}
		return
	}
	if res.NewName == "" {
		logger.Infof("AI returned empty name for %s, skipping", path)
		return
	}

	originalName := filepath.Base(path)
	dir := filepath.Dir(path)
	ext := filepath.Ext(path)
	dest := filepath.Join(dir, res.NewName+ext)

	if err := os.Rename(path, dest); err != nil {
		logger.Errorf("rename %s->%s failed: %v", path, dest, err)
		if e.bus != nil {
			e.bus.Emit(events.Event{
				Type:     events.EventFileError,
				Source:   dir,
				Detail:   fmt.Sprintf("Rename failed: %s -> %s: %v", originalName, res.NewName+ext, err),
				Metadata: map[string]string{"path": path, "error": err.Error()},
			})
		}
		return
	}
	logger.Infof("Renamed %s to %s", path, dest)

	// Emit success event
	if e.bus != nil {
		e.bus.Emit(events.Event{
			Type:   events.EventFileMoved,
			Source: dir,
			Detail: fmt.Sprintf("%s -> %s", originalName, res.NewName+ext),
			Metadata: map[string]string{
				"original_path": path,
				"new_path":      dest,
				"new_name":      res.NewName + ext,
				"original_name": originalName,
			},
		})
	}

	// Update DB with new path and metadata
	info, err := os.Stat(dest)
	if err == nil {
		e.upsertFile(dest, originalName, info.Size(), info.ModTime(), res.Metadata, res.Context)
	}

	// ponytail: minimal vault generation
	if e.cfg.VaultPath != "" {
		os.MkdirAll(e.cfg.VaultPath, 0755)
		vContent := fmt.Sprintf("# %s\n\n**Original Path:** %s\n**Date Organized:** %s\n**Metadata:** %s\n\n## Context\n%s",
			res.NewName, path, time.Now().Format("2006-01-02"), res.Metadata, res.Context)
		os.WriteFile(filepath.Join(e.cfg.VaultPath, res.NewName+".md"), []byte(vContent), 0644)
	}
}

func (e *Engine) Close() error {
	if e.stopCh != nil {
		close(e.stopCh)
	}
	if e.watcher != nil {
		e.watcher.Close()
	}
	return e.db.Close()
}
