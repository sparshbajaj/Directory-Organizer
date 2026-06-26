package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "directory-organizer",
	Short: "Directory Organizer - watch and index your files",
	Long:  `A Go implementation of the Directory Organizer application with watching, indexing, and AI assistance.`,
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("Use a subcommand: scan, watch, serve, or version.")
	},
}

// Execute runs the root command.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

func init() {
	rootCmd.AddCommand(scanCmd)
}
