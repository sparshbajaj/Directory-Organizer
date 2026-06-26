package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/sparshbajaj/directory-organizer/internal/aiclient"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/spf13/cobra"
)

var initCmd = &cobra.Command{
	Use:   "init",
	Short: "Interactive first-time setup with your AI CLI",
	Long: `Runs an interactive AI-assisted setup to configure file organization rules.
Auto-installs the chosen CLI, helps you log in, then launches it to explore
the watch directory, ask you questions, and generate rules.`,
	RunE: runInit,
}

func init() {
	rootCmd.AddCommand(initCmd)
}

func runInit(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	cliName := cfg.AICLIProvider
	if cliName == "" {
		cliName = os.Getenv("VAULTSORT_AI_CLI")
	}
	if cliName == "" {
		cliName = promptChoice("Which AI CLI do you want to use?", []string{"opencode", "claude", "antigravity"})
		cfg.AICLIProvider = cliName
		config.Save(cfg)
	}

	dir := cfg.WatchDir
	dataDir := aiclient.DataDir()

	provider := aiclient.NewCLIProvider(cliName, cliName, cfg.RulesPath, dataDir)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigCh
		cancel()
	}()

	if !provider.IsInstalled() {
		fmt.Printf("\n🔍 %s not found. Installing...\n", cliName)
		if err := provider.Install(ctx); err != nil {
			return fmt.Errorf("install %s: %w", cliName, err)
		}
	} else {
		fmt.Printf("\n✅ %s already installed\n", cliName)
	}

	fmt.Printf("\n🔐 Let's log into %s\n", cliName)
	fmt.Println("Follow the prompts to authenticate. Your session will persist across restarts.")
	if err := provider.Login(ctx); err != nil {
		return fmt.Errorf("login %s: %w", cliName, err)
	}

	fmt.Printf("\n🔍 Setting up %s to organize: %s\n", cliName, dir)
	fmt.Println("The CLI will explore your files and ask questions to build rules.")
	fmt.Println("Answer its questions to teach it your preferences.")
	fmt.Println()

	if err := provider.InitRules(ctx, dir); err != nil {
		return fmt.Errorf("init rules: %w", err)
	}

	fmt.Println("\n✅ Setup complete! VaultSort will now use these rules")
	fmt.Println("and improve them over time as it processes more files.")
	logger.Infof("Initial setup completed with %s for %s", cliName, dir)
	return nil
}

func promptChoice(question string, options []string) string {
	fmt.Println(question)
	for i, opt := range options {
		fmt.Printf("  %d. %s\n", i+1, opt)
	}
	fmt.Print("Enter number (default 1): ")
	var input string
	fmt.Scanln(&input)
	if input == "" {
		return options[0]
	}
	for i, opt := range options {
		if fmt.Sprintf("%d", i+1) == input {
			return opt
		}
	}
	return options[0]
}
