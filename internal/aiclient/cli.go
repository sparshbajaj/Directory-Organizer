package aiclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

var cliInstalls = map[string]struct {
	pkg      string // npm package name
	binary   string // binary name after install
	config   string // relative dir under configHome
	loginCmd []string
}{
	"opencode": {
		pkg:      "opencode-ai",
		binary:   "opencode",
		config:   "opencode",
		loginCmd: []string{"providers", "login"},
	},
	"claude": {
		pkg:      "@anthropic-ai/claude-cli",
		binary:   "claude",
		config:   ".claude",
		loginCmd: []string{"login"},
	},
	"antigravity": {
		pkg:      "antigravity",
		binary:   "antigravity",
		config:   "antigravity",
		loginCmd: []string{"login"},
	},
}

type CLIProvider struct {
	binary     string
	name       string
	rulesDB    string
	dataDir    string
	configHome string
}

func NewCLIProvider(binary, name, rulesDB, dataDir string) *CLIProvider {
	configHome := filepath.Join(dataDir, "configs")
	return &CLIProvider{
		binary:     binary,
		name:       name,
		rulesDB:    rulesDB,
		dataDir:    dataDir,
		configHome: configHome,
	}
}

func (p *CLIProvider) Name() string { return p.name }

func (p *CLIProvider) binaryPath() string {
	return filepath.Join(p.dataDir, "clis", p.name, p.name)
}

func (p *CLIProvider) configPath() string {
	return filepath.Join(p.configHome, p.name)
}

func (p *CLIProvider) IsInstalled() bool {
	if _, err := os.Stat(p.binaryPath()); err == nil {
		return true
	}
	if _, err := exec.LookPath(p.name); err == nil {
		return true
	}
	return false
}

func (p *CLIProvider) Install(ctx context.Context) error {
	installDir := filepath.Join(p.dataDir, "clis", p.name)
	if err := os.MkdirAll(installDir, 0755); err != nil {
		return fmt.Errorf("mkdir install dir: %w", err)
	}

	info, ok := cliInstalls[p.name]
	if !ok {
		return fmt.Errorf("no install method for %s", p.name)
	}

	dest := p.binaryPath()
	if _, err := os.Stat(dest); err == nil {
		fmt.Printf("✅ %s already installed at %s\n", p.name, dest)
		return nil
	}

	fmt.Printf("📥 Installing %s via npm (persisted to %s)...\n", p.name, installDir)

	npmCmd := exec.CommandContext(ctx, "npm", "install", "-g", info.pkg)
	npmCmd.Stdout = os.Stdout
	npmCmd.Stderr = os.Stderr
	if err := npmCmd.Run(); err != nil {
		return fmt.Errorf("npm install %s failed: %w", info.pkg, err)
	}

	which, err := exec.LookPath(info.binary)
	if err != nil {
		return fmt.Errorf("%s not found after npm install: %v", info.binary, err)
	}

	copyCmd := exec.CommandContext(ctx, "cp", which, dest)
	if err := copyCmd.Run(); err != nil {
		return fmt.Errorf("copy binary to %s: %w", dest, err)
	}
	os.Chmod(dest, 0755)
	fmt.Printf("✅ %s installed to %s\n", p.name, dest)

	return nil
}

func (p *CLIProvider) ensurePath() string {
	bp := p.binaryPath()
	if _, err := os.Stat(bp); err == nil {
		return bp
	}
	return p.name
}

func (p *CLIProvider) Login(ctx context.Context) error {
	binary := p.ensurePath()
	configDir := p.configPath()
	os.MkdirAll(configDir, 0755)

	info, ok := cliInstalls[p.name]
	if !ok || len(info.loginCmd) == 0 {
		fmt.Printf("⚠️  No login method configured for %s\n", p.name)
		return nil
	}

	fmt.Printf("\n🔐 Logging into %s\n", p.name)
	fmt.Printf("Config will be saved to %s (persists across restarts)\n", configDir)

	args := info.loginCmd
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Env = append(os.Environ(),
		"XDG_CONFIG_HOME="+p.configHome,
		"HOME="+filepath.Join(p.dataDir, "home"),
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	return cmd.Run()
}

func (p *CLIProvider) Analyze(ctx context.Context, path, prompt string) (*AIResult, error) {
	binary := p.ensurePath()

	fullPrompt := fmt.Sprintf(`%s

Analyze the file at %s.
Read its contents, understand what it is.
Output ONLY a raw JSON object with the keys: new_name (descriptive new filename without extension), metadata (comma-separated tags/keywords), context (brief summary).
Do not output any markdown formatting or extra text.`, prompt, path)

	attempts := 3
	var lastErr error
	for i := 0; i < attempts; i++ {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
		}

		cmd := exec.CommandContext(ctx, binary, "-p", fullPrompt)
		cmd.Env = append(os.Environ(),
			"XDG_CONFIG_HOME="+p.configHome,
			"HOME="+filepath.Join(p.dataDir, "home"),
		)
		var stdout, stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		if err := cmd.Run(); err != nil {
			lastErr = fmt.Errorf("%s run: %w\nstderr: %s", p.name, err, stderr.String())
			time.Sleep(time.Second)
			continue
		}

		content := strings.TrimSpace(stdout.String())
		content = strings.TrimPrefix(content, "```json")
		content = strings.TrimPrefix(content, "```")
		content = strings.TrimSuffix(content, "```")
		content = strings.TrimSpace(content)

		var res AIResult
		if err := json.Unmarshal([]byte(content), &res); err != nil {
			lastErr = fmt.Errorf("parse %s JSON: %v\nraw: %s", p.name, err, content)
			continue
		}

		res.NewName = sanitizeFilename(res.NewName)
		if res.NewName == "" {
			lastErr = fmt.Errorf("empty new_name from %s", p.name)
			continue
		}

		return &res, nil
	}

	return nil, lastErr
}

func (p *CLIProvider) InitRules(ctx context.Context, dir string) error {
	binary := p.ensurePath()
	prompt := fmt.Sprintf(`I need to set up automated file organization rules for the directory %s.

First, explore the directory structure and look at the files there.
Ask me questions to understand:
1. How I want files categorized (by type, date, project, etc.)
2. What naming conventions I prefer
3. Which subdirectories to create and what goes where

After we've discussed, generate a JSON rules file at %s with the following format:
[
  {
    "pattern": "*.jpg",
    "new_name": "{{date}}_{{original}}",
    "target_dir": "Images",
    "metadata": "image,photo",
    "context": "Photographs and images"
  }
]

Let's start by analyzing the directory.`, dir, p.rulesDB)

	// Try opencode-style first (run <message>)
	runCmd := exec.CommandContext(ctx, binary, "run", prompt)
	runCmd.Env = append(os.Environ(),
		"XDG_CONFIG_HOME="+p.configHome,
		"HOME="+filepath.Join(p.dataDir, "home"),
	)
	runCmd.Stdout = os.Stdout
	runCmd.Stderr = os.Stderr
	runCmd.Stdin = os.Stdin
	if err := runCmd.Run(); err == nil {
		return nil
	}

	// Fallback: try --prompt flag
	cmd := exec.CommandContext(ctx, binary, "-p", prompt, dir)
	cmd.Env = append(os.Environ(),
		"XDG_CONFIG_HOME="+p.configHome,
		"HOME="+filepath.Join(p.dataDir, "home"),
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Run(); err != nil {
		fmt.Printf("⚠️  Could not auto-generate rules via CLI.\n")
		fmt.Printf("   Rules will be learned automatically as files are processed.\n")
		fmt.Printf("   To generate rules manually, run: %s\n", binary)
	}
	return nil
}

func DataDir() string {
	if d := os.Getenv("VAULTSORT_DATA_DIR"); d != "" {
		return d
	}
	if d := os.Getenv("APPDATA"); d != "" {
		return filepath.Join(d, "DirectoryOrganizer")
	}
	return "/data"
}
