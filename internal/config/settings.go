// internal/config/settings.go
package config

import (
    "encoding/json"
    "os"
    "path/filepath"
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

    // Save defaults to file so the user can modify them
    Save(&s)

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
