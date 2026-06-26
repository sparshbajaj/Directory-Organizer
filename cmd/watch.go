// cmd/watch.go
package cmd

import (
	"os"
	"os/signal"
	"syscall"

	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/sparshbajaj/directory-organizer/internal/watcher"
	"github.com/spf13/cobra"
)

var watchCmd = &cobra.Command{
	Use:   "watch",
	Short: "Start watching the directory for changes in the foreground",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load()
		if err != nil {
			return err
		}

		eng, err := engine.NewEngine(cfg)
		if err != nil {
			return err
		}
		defer eng.Close()

		w, err := watcher.New(eng)
		if err != nil {
			return err
		}

		if err := w.AddRoots([]string{cfg.WatchDir}); err != nil {
			return err
		}

		stopCh := make(chan struct{})
		go w.Run(stopCh)

		logger.Infof("Watching directory %s. Press Ctrl+C to stop.", cfg.WatchDir)

		// Wait for interrupt
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		logger.Info("Stopping watcher...")
		close(stopCh)
		return nil
	},
}

func init() {
	rootCmd.AddCommand(watchCmd)
}
