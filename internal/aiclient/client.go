// internal/aiclient/client.go
package aiclient

import (
    "context"
    "encoding/json"
    "fmt"
    "os/exec"
    "strings"
    "time"

    "github.com/sparshbajaj/directory-organizer/internal/config"
)

type Client struct {
    cfg *config.Settings
}

type AIResult struct {
    NewName  string `json:"new_name"`
    Metadata string `json:"metadata"`
    Context  string `json:"context"`
}

func New(cfg *config.Settings) (*Client, error) {
    return &Client{cfg: cfg}, nil
}

// Analyze calls the agy CLI to get a new filename, metadata, and context.
func (c *Client) Analyze(ctx context.Context, filePath string) (*AIResult, error) {
    prompt := fmt.Sprintf(`Analyze the file at %s. Extract its metadata, summarize its context, and determine a highly descriptive new filename. 
Output ONLY a raw JSON object with the keys: new_name, metadata, context. 
Do not output any markdown formatting or extra text.`, filePath)

    args := []string{"-p", prompt, "-o", "text", "-y"}
    if c.cfg.APIKey != "" {
        args = append(args, "--api-key", c.cfg.APIKey)
    }
    if c.cfg.Model != "" {
        args = append(args, "--model", c.cfg.Model)
    }
    if c.cfg.BaseURL != "" && c.cfg.BaseURL != "http://localhost:11434/v1" {
        args = append(args, "--base-url", c.cfg.BaseURL)
    }

    // Retry logic
    attempts := c.cfg.Retries + 1
    if attempts <= 0 {
        attempts = 1
    }

    var lastErr error
    for i := 0; i < attempts; i++ {
        cmd := exec.CommandContext(ctx, "agy", args...)
        output, err := cmd.CombinedOutput()
        
        if err != nil {
            lastErr = fmt.Errorf("agy cli error: %v, output: %s", err, string(output))
            time.Sleep(time.Duration(c.cfg.RetryBackoff*float64(i+1)) * time.Second)
            continue
        }

        // Output might have surrounding backticks or spaces
        raw := strings.TrimSpace(string(output))
        raw = strings.TrimPrefix(raw, "```json")
        raw = strings.TrimPrefix(raw, "```")
        raw = strings.TrimSuffix(raw, "```")
        raw = strings.TrimSpace(raw)

        var res AIResult
        if err := json.Unmarshal([]byte(raw), &res); err != nil {
            lastErr = fmt.Errorf("failed to parse AI JSON: %v, raw: %s", err, raw)
            time.Sleep(time.Duration(c.cfg.RetryBackoff*float64(i+1)) * time.Second)
            continue
        }

        res.NewName = sanitizeFilename(res.NewName)
        if res.NewName == "" {
            lastErr = fmt.Errorf("empty new_name from AI")
            time.Sleep(time.Duration(c.cfg.RetryBackoff*float64(i+1)) * time.Second)
            continue
        }

        return &res, nil
    }

    return nil, lastErr
}

// Very small sanitiser to ensure filename safety
func sanitizeFilename(name string) string {
    cleaned := name
    cleaned = strings.TrimSpace(cleaned)
    cleaned = strings.Trim(cleaned, "\"'")
    cleaned = strings.ReplaceAll(cleaned, "\n", "")
    cleaned = strings.ReplaceAll(cleaned, "\r", "")
    illegal := []string{"/", "\\", ":", "*", "?", "\"", "<", ">", "|"}
    for _, r := range illegal {
        cleaned = strings.ReplaceAll(cleaned, r, "_")
    }
    if len([]rune(cleaned)) > 255 {
        cleaned = string([]rune(cleaned)[:255])
    }
    return cleaned
}
