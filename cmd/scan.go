// cmd/scan.go
package cmd

import (
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/spf13/cobra"
)

var scanCmd = &cobra.Command{
	Use:   "scan",
	Short: "Recursively scan the watch directory and index files",
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
		return eng.ScanDirectory()
	},
}

func init() {
	rootCmd.AddCommand(scanCmd)
}
