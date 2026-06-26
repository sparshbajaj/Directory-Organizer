// internal/aiclient/client.go
package aiclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
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

// Analyze calls the configured OpenAI-compatible API to get a new filename, metadata, and context.
func (c *Client) Analyze(ctx context.Context, filePath string) (*AIResult, error) {
	// ponytail: minimum viable file read
	content, _ := os.ReadFile(filePath)
	if len(content) > 2000 {
		content = content[:2000]
	}
	contentStr := strings.ToValidUTF8(string(content), "")

	prompt := fmt.Sprintf(`Analyze the file at %s.
File contents snippet:
%s

Extract its metadata, summarize its context, and determine a highly descriptive new filename. 
Output ONLY a raw JSON object with the keys: new_name, metadata, context. 
Do not output any markdown formatting or extra text.`, filePath, contentStr)

	baseURL := c.cfg.BaseURL
	if baseURL == "" {
		baseURL = "http://localhost:11434/v1"
	}
	// Ensure we hit the chat completions endpoint
	if !strings.HasSuffix(baseURL, "/chat/completions") {
		baseURL = strings.TrimSuffix(baseURL, "/") + "/chat/completions"
	}

	model := c.cfg.Model
	if model == "" {
		model = "auto"
	}

	reqBody := map[string]interface{}{
		"model": model,
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
		"temperature": 0.2,
	}
	bodyBytes, _ := json.Marshal(reqBody)

	attempts := c.cfg.Retries + 1
	if attempts <= 0 {
		attempts = 1
	}

	var lastErr error
	for i := 0; i < attempts; i++ {
		req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(bodyBytes))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		if c.cfg.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+c.cfg.APIKey)
		}

		client := &http.Client{Timeout: 2 * time.Minute}
		resp, err := client.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("API request failed: %v", err)
			time.Sleep(time.Duration(c.cfg.RetryBackoff*float64(i+1)) * time.Second)
			continue
		}

		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("API error %d: %s", resp.StatusCode, string(respBody))
			time.Sleep(time.Duration(c.cfg.RetryBackoff*float64(i+1)) * time.Second)
			continue
		}

		// Parse OpenAI format
		var aiResp struct {
			Choices []struct {
				Message struct {
					Content string `json:"content"`
				} `json:"message"`
			} `json:"choices"`
		}
		if err := json.Unmarshal(respBody, &aiResp); err != nil {
			lastErr = fmt.Errorf("failed to parse AI response: %v, body: %s", err, string(respBody))
			continue
		}
		if len(aiResp.Choices) == 0 {
			lastErr = fmt.Errorf("no choices in AI response")
			continue
		}

		content := strings.TrimSpace(aiResp.Choices[0].Message.Content)
		content = strings.TrimPrefix(content, "```json")
		content = strings.TrimPrefix(content, "```")
		content = strings.TrimSuffix(content, "```")
		content = strings.TrimSpace(content)

		var res AIResult
		if err := json.Unmarshal([]byte(content), &res); err != nil {
			lastErr = fmt.Errorf("failed to parse AI JSON content: %v, raw: %s", err, content)
			continue
		}

		res.NewName = sanitizeFilename(res.NewName)
		if res.NewName == "" {
			lastErr = fmt.Errorf("empty new_name from AI")
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
