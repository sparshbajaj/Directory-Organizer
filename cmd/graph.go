package cmd

import (
	"fmt"

	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/knowledge"
	"github.com/spf13/cobra"
)

var graphCmd = &cobra.Command{
	Use:   "graph",
	Short: "Export the knowledge graph as JSON",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load()
		if err != nil {
			return fmt.Errorf("config: %w", err)
		}
		kbPath := cfg.KBPath
		if kbPath == "" {
			kbPath = cfg.DBPath
		}
		kb, err := knowledge.New(kbPath)
		if err != nil {
			return fmt.Errorf("kb: %w", err)
		}
		defer kb.Close()

		if err := kb.BuildGraph(cfg.WatchDir); err != nil {
			return fmt.Errorf("build graph: %w", err)
		}

		graph, err := kb.ExportGraphJSON()
		if err != nil {
			return fmt.Errorf("export: %w", err)
		}
		fmt.Println(graph)
		return nil
	},
}

func init() {
	rootCmd.AddCommand(graphCmd)
}
