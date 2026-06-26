// internal/updater/updater.go
package updater

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
)

// Release represents a GitHub release.
type Release struct {
	TagName     string `json:"tag_name"`
	Name        string `json:"name"`
	HTMLURL     string `json:"html_url"`
	Body        string `json:"body"`
	PublishedAt string `json:"published_at"`
}

// Updater periodically checks GitHub for new releases.
type Updater struct {
	owner    string
	repo     string
	current  string
	interval time.Duration
	latest   *Release
	mu       sync.RWMutex
}

// New creates a new Updater that checks the given GitHub repository for updates.
func New(owner, repo, currentVersion string, interval time.Duration) *Updater {
	return &Updater{
		owner:    owner,
		repo:     repo,
		current:  currentVersion,
		interval: interval,
	}
}

// Start begins the periodic update check loop in a goroutine.
// It checks immediately, then on the configured interval.
func (u *Updater) Start(ctx context.Context, bus *events.Bus) {
	// Check immediately
	u.checkAndEmit(bus)

	ticker := time.NewTicker(u.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			logger.Info("Update checker stopped")
			return
		case <-ticker.C:
			u.checkAndEmit(bus)
		}
	}
}

// checkAndEmit performs a single update check and emits an event if a new version is found.
func (u *Updater) checkAndEmit(bus *events.Bus) {
	rel, err := u.CheckLatest()
	if err != nil {
		logger.Errorf("Update check failed: %v", err)
		return
	}

	u.mu.Lock()
	u.latest = rel
	u.mu.Unlock()

	if u.HasUpdate() && bus != nil {
		bus.Emit(events.Event{
			Type:   events.EventUpdateAvail,
			Detail: fmt.Sprintf("New version available: %s", rel.TagName),
			Metadata: map[string]string{
				"tag":     rel.TagName,
				"name":    rel.Name,
				"url":     rel.HTMLURL,
				"current": u.current,
			},
		})
		logger.Infof("New version available: %s (current: %s)", rel.TagName, u.current)
	}
}

// CheckLatest fetches the latest release from GitHub.
func (u *Updater) CheckLatest() (*Release, error) {
	url := fmt.Sprintf("https://api.github.com/repos/%s/%s/releases/latest", u.owner, u.repo)

	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("User-Agent", fmt.Sprintf("VaultSort/%s", u.current))
	req.Header.Set("Accept", "application/vnd.github.v3+json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http get: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github api: status %d", resp.StatusCode)
	}

	var rel Release
	if err := json.NewDecoder(resp.Body).Decode(&rel); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &rel, nil
}

// Latest returns the most recently fetched release in a thread-safe manner.
func (u *Updater) Latest() *Release {
	u.mu.RLock()
	defer u.mu.RUnlock()
	return u.latest
}

// HasUpdate returns true if a newer version is available on GitHub.
func (u *Updater) HasUpdate() bool {
	u.mu.RLock()
	defer u.mu.RUnlock()
	return u.latest != nil && u.latest.TagName != u.current
}
