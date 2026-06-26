package cmd

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/dashboard"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/sparshbajaj/directory-organizer/internal/scheduler"
	"github.com/sparshbajaj/directory-organizer/internal/updater"
	"github.com/sparshbajaj/directory-organizer/internal/watcher"
	_ "modernc.org/sqlite"
)

var (
	Version   = "dev"
	BuildTime = "unknown"
)

var daemonCmd = &cobra.Command{
	Use:   "daemon",
	Short: "Run as a headless daemon (for Docker/background operation)",
	Long: `Runs VaultSort in headless daemon mode, reading configuration from
environment variables. Starts file watchers, interval scanners, web dashboard,
and GitHub update checker. Designed for 24/7 Docker deployments.`,
	RunE: runDaemon,
}

func init() {
	rootCmd.AddCommand(daemonCmd)
}

func runDaemon(cmd *cobra.Command, args []string) error {
	// 1. Load config from environment
	cfg, err := config.LoadFromEnv()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	// 2. Parse durations
	interval, err := time.ParseDuration(cfg.IntervalStr)
	if err != nil {
		interval = 5 * time.Minute
	}
	ghInterval, err := time.ParseDuration(cfg.GitHubIntervalStr)
	if err != nil {
		ghInterval = 6 * time.Hour
	}

	// 3. Ensure directories exist
	for _, dir := range cfg.WatchDirs {
		if err := os.MkdirAll(dir, 0755); err != nil {
			logger.Errorf("Failed to create directory %s: %v", dir, err)
		}
	}
	if cfg.VaultPath != "" {
		os.MkdirAll(cfg.VaultPath, 0755)
	}

	// 4. Open database
	os.MkdirAll(filepath.Dir(cfg.DBPath), 0755)
	db, err := sql.Open("sqlite", cfg.DBPath)
	if err != nil {
		return fmt.Errorf("open db: %w", err)
	}
	defer db.Close()

	// 5. Create event bus
	bus, err := events.NewBus(db)
	if err != nil {
		return fmt.Errorf("event bus: %w", err)
	}

	// 6. Create engine
	eng, err := engine.NewEngine(cfg)
	if err != nil {
		return fmt.Errorf("engine: %w", err)
	}
	eng.SetBus(bus)
	defer eng.Close()

	// 7. Context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 8. Start watchers (if mode is "watch" or "both")
	if cfg.Mode == "watch" || cfg.Mode == "both" {
		w, err := watcher.New(eng)
		if err != nil {
			logger.Errorf("Failed to create watcher: %v", err)
		} else {
			if err := w.AddRoots(cfg.WatchDirs); err != nil {
				logger.Errorf("Failed to add watch roots: %v", err)
			}
			stopCh := make(chan struct{})
			go w.Run(stopCh)
			defer close(stopCh)
			for _, d := range cfg.WatchDirs {
				bus.Emit(events.Event{
					Type:   events.EventWatcherStart,
					Source: d,
					Detail: fmt.Sprintf("Watcher started for %s", d),
				})
			}
			logger.Infof("File watchers started for %d directories", len(cfg.WatchDirs))
		}
	}

	// 9. Start scheduler (if mode is "interval" or "both")
	if cfg.Mode == "interval" || cfg.Mode == "both" {
		sched := scheduler.New(cfg.WatchDirs, interval, eng, bus)
		go sched.Start(ctx)
		logger.Infof("Interval scheduler started (every %s)", interval)
	}

	// 10. Start GitHub updater
	var upd *updater.Updater
	if cfg.GitHubCheck {
		upd = updater.New("sparshbajaj", "Directory-Organizer", Version, ghInterval)
		go upd.Start(ctx, bus)
		logger.Info("GitHub update checker started")
	}

	// 11. Start web dashboard
	srv := dashboard.NewServer(bus, upd, eng.AIClient(), cfg, Version)
	go func() {
		if err := srv.Start(ctx, cfg.Port); err != nil {
			logger.Errorf("Dashboard server error: %v", err)
		}
	}()
	logger.Infof("Web dashboard started on port %d", cfg.Port)

	// 12. Emit system start event
	bus.Emit(events.Event{
		Type: events.EventSystemStart,
		Detail: fmt.Sprintf("VaultSort daemon v%s started | Mode: %s | Dirs: %d | Port: %d",
			Version, cfg.Mode, len(cfg.WatchDirs), cfg.Port),
	})

	// Print startup banner
	fmt.Println("╔══════════════════════════════════════════════════╗")
	fmt.Println("║          🗂️  VaultSort Daemon Started             ║")
	fmt.Printf("║  Version:   %-37s ║\n", Version)
	fmt.Printf("║  Mode:      %-37s ║\n", cfg.Mode)
	fmt.Printf("║  Dirs:      %-37d ║\n", len(cfg.WatchDirs))
	fmt.Printf("║  Interval:  %-37s ║\n", interval)
	fmt.Printf("║  Dashboard: http://0.0.0.0:%-23d ║\n", cfg.Port)
	fmt.Println("╚══════════════════════════════════════════════════╝")

	// 13. Wait for shutdown signal
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	logger.Info("Shutdown signal received, stopping daemon...")
	cancel()
	return nil
}
