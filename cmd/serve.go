// cmd/serve.go
package cmd

import (
	"github.com/kardianos/service"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/sparshbajaj/directory-organizer/internal/watcher"
	"github.com/spf13/cobra"
)

type program struct {
	eng    *engine.Engine
	w      *watcher.Watcher
	stopCh chan struct{}
}

func (p *program) Start(s service.Service) error {
	logger.Info("Starting service...")

	cfg, err := config.Load()
	if err != nil {
		return err
	}

	eng, err := engine.NewEngine(cfg)
	if err != nil {
		return err
	}
	p.eng = eng

	w, err := watcher.New(eng)
	if err != nil {
		return err
	}
	p.w = w

	if err := w.AddRoots([]string{cfg.WatchDir}); err != nil {
		return err
	}

	p.stopCh = make(chan struct{})
	go p.w.Run(p.stopCh)
	return nil
}

func (p *program) Stop(s service.Service) error {
	logger.Info("Stopping service...")
	if p.stopCh != nil {
		close(p.stopCh)
	}
	if p.eng != nil {
		p.eng.Close()
	}
	return nil
}

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Run as a Windows service",
	RunE: func(cmd *cobra.Command, args []string) error {
		svcConfig := &service.Config{
			Name:        "DirectoryOrganizer",
			DisplayName: "Directory Organizer Service",
			Description: "Monitors a directory and renames files using AI.",
		}

		prg := &program{}
		s, err := service.New(prg, svcConfig)
		if err != nil {
			return err
		}

		if len(args) > 0 {
			if args[0] == "install" {
				return s.Install()
			}
			if args[0] == "uninstall" {
				return s.Uninstall()
			}
			if args[0] == "start" {
				return s.Start()
			}
			if args[0] == "stop" {
				return s.Stop()
			}
		}

		return s.Run()
	},
}

func init() {
	rootCmd.AddCommand(serveCmd)
}
