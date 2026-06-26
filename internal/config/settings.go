// internal/config/settings.go
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

var SettingsPath string

func init() {
	appData := os.Getenv("APPDATA")
	if appData == "" {
		// fallback to user home
		home, _ := os.UserHomeDir()
		appData = home
	}
	SettingsPath = filepath.Join(appData, "DirectoryOrganizer", "settings.json")
}

type Settings struct {
	// Add any configuration fields you need
	AIProvider   string  `json:"ai_provider"`
	APIKey       string  `json:"api_key"`
	BaseURL      string  `json:"base_url"`
	Model        string  `json:"model"`
	VisionModel  string  `json:"vision_model"`
	SendContent  bool    `json:"send_content"`
	RetryBackoff float64 `json:"retry_backoff"`
	Retries      int     `json:"retries"`
	Temperature  float64 `json:"temperature"`
	MaxTokens    int     `json:"max_tokens"`
	WatchDir     string  `json:"watch_dir"`
	DBPath       string  `json:"db_path"`
	WatchPath    string  `json:"watch_path"`

	// Daemon mode fields
	WatchDirs         []string `json:"watch_dirs,omitempty"`
	Mode              string   `json:"mode,omitempty"`
	IntervalStr       string   `json:"interval,omitempty"`
	Port              int      `json:"port,omitempty"`
	VaultPath         string   `json:"vault_path,omitempty"`
	LogLevel          string   `json:"log_level,omitempty"`
	GitHubCheck       bool     `json:"github_check,omitempty"`
	GitHubIntervalStr string   `json:"github_interval,omitempty"`
	ServerURL         string   `json:"server_url,omitempty"`
}

func Load() (*Settings, error) {
	var s Settings
	data, err := os.ReadFile(SettingsPath)
	if err == nil {
		if err := json.Unmarshal(data, &s); err != nil {
			return nil, err
		}
	} else if !os.IsNotExist(err) {
		return nil, err
	}

	// Set defaults
	appData := os.Getenv("APPDATA")
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = home
	}
	base := filepath.Join(appData, "DirectoryOrganizer")
	if s.WatchDir == "" {
		s.WatchDir = filepath.Join(base, "watch")
	}
	if s.DBPath == "" {
		s.DBPath = filepath.Join(base, "organizer.db")
	}
	if s.BaseURL == "" {
		s.BaseURL = "http://localhost:11434/v1"
	}

	// Save defaults only if file didn't exist (don't overwrite user edits)
	if os.IsNotExist(err) {
		Save(&s)
	}

	return &s, nil
}

func Save(s *Settings) error {
	dir := filepath.Dir(SettingsPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(SettingsPath, data, 0644)
}

// LoadFromEnv creates a Settings from environment variables (for Docker/daemon mode).
func LoadFromEnv() (*Settings, error) {
	s := &Settings{}

	// VAULTSORT_DIRS (required)
	dirsStr := os.Getenv("VAULTSORT_DIRS")
	if dirsStr == "" {
		return nil, fmt.Errorf("VAULTSORT_DIRS is required")
	}
	for _, d := range strings.Split(dirsStr, ",") {
		d = strings.TrimSpace(d)
		if d != "" {
			s.WatchDirs = append(s.WatchDirs, d)
		}
	}
	if len(s.WatchDirs) == 0 {
		return nil, fmt.Errorf("VAULTSORT_DIRS is required")
	}

	// WatchDir = first entry for backward compat
	s.WatchDir = s.WatchDirs[0]

	// VAULTSORT_MODE (default "watch")
	s.Mode = os.Getenv("VAULTSORT_MODE")
	if s.Mode == "" {
		s.Mode = "watch"
	}

	// VAULTSORT_INTERVAL (default "5m")
	s.IntervalStr = os.Getenv("VAULTSORT_INTERVAL")
	if s.IntervalStr == "" {
		s.IntervalStr = "5m"
	}

	// VAULTSORT_PORT (default 8080)
	portStr := os.Getenv("VAULTSORT_PORT")
	if portStr != "" {
		p, err := strconv.Atoi(portStr)
		if err != nil {
			return nil, fmt.Errorf("invalid VAULTSORT_PORT: %w", err)
		}
		s.Port = p
	} else {
		s.Port = 8080
	}

	// VAULTSORT_DB_PATH (default "/data/vaultsort.db")
	s.DBPath = os.Getenv("VAULTSORT_DB_PATH")
	if s.DBPath == "" {
		s.DBPath = "/data/vaultsort.db"
	}

	// VAULTSORT_VAULT_PATH (default "/data/vault")
	s.VaultPath = os.Getenv("VAULTSORT_VAULT_PATH")
	if s.VaultPath == "" {
		s.VaultPath = "/data/vault"
	}

	// VAULTSORT_LOG_LEVEL (default "info")
	s.LogLevel = os.Getenv("VAULTSORT_LOG_LEVEL")
	if s.LogLevel == "" {
		s.LogLevel = "info"
	}

	// VAULTSORT_GITHUB_CHECK (default true)
	ghCheck := os.Getenv("VAULTSORT_GITHUB_CHECK")
	if strings.EqualFold(ghCheck, "false") {
		s.GitHubCheck = false
	} else {
		s.GitHubCheck = true
	}

	// VAULTSORT_GITHUB_INTERVAL (default "6h")
	s.GitHubIntervalStr = os.Getenv("VAULTSORT_GITHUB_INTERVAL")
	if s.GitHubIntervalStr == "" {
		s.GitHubIntervalStr = "6h"
	}

	// Set retry defaults
	s.Retries = 3
	s.RetryBackoff = 2.0

	// Read AI config from env if available
	if v := os.Getenv("VAULTSORT_AI_PROVIDER"); v != "" {
		s.AIProvider = v
	}
	if v := os.Getenv("VAULTSORT_API_KEY"); v != "" {
		s.APIKey = v
	}
	if v := os.Getenv("VAULTSORT_BASE_URL"); v != "" {
		s.BaseURL = v
	}
	if s.BaseURL == "" {
		s.BaseURL = "http://localhost:11434/v1"
	}
	if v := os.Getenv("VAULTSORT_MODEL"); v != "" {
		s.Model = v
	}
	if v := os.Getenv("VAULTSORT_SERVER_URL"); v != "" {
		s.ServerURL = v
	}

	return s, nil
}
