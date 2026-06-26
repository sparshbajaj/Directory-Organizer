// internal/scheduler/scheduler.go
package scheduler

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
)

// Scheduler periodically scans directories and enqueues new or modified files.
// This is useful for remote/network mounts where fsnotify doesn't work.
type Scheduler struct {
	dirs     []string
	interval time.Duration
	engine   *engine.Engine
	bus      *events.Bus
	known    map[string]int64
	mu       sync.RWMutex
}

// New creates a new Scheduler that scans the given directories at the specified interval.
func New(dirs []string, interval time.Duration, eng *engine.Engine, bus *events.Bus) *Scheduler {
	return &Scheduler{
		dirs:     dirs,
		interval: interval,
		engine:   eng,
		bus:      bus,
		known:    make(map[string]int64),
	}
}

// Start begins the periodic scanning loop. It blocks until ctx is cancelled.
func (s *Scheduler) Start(ctx context.Context) {
	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()

	// Run an initial scan immediately
	s.scanOnce()

	for {
		select {
		case <-ctx.Done():
			logger.Info("Scheduler stopped")
			return
		case <-ticker.C:
			s.scanOnce()
		}
	}
}

// scanOnce performs a single scan of all watched directories.
func (s *Scheduler) scanOnce() {
	// Emit scheduler tick event
	if s.bus != nil {
		s.bus.Emit(events.Event{
			Type:   events.EventSchedulerTick,
			Detail: "Interval scan started",
		})
	}

	for _, dir := range s.dirs {
		err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				logger.Errorf("Scheduler walk error: %v", err)
				return nil // continue walking
			}

			// Skip hidden directories
			if info.IsDir() {
				if strings.HasPrefix(info.Name(), ".") {
					return filepath.SkipDir
				}
				return nil
			}

			modTime := info.ModTime().UnixNano()

			s.mu.RLock()
			knownMod, exists := s.known[path]
			s.mu.RUnlock()

			// Enqueue if new file or modified since last scan
			if !exists || knownMod != modTime {
				s.mu.Lock()
				s.known[path] = modTime
				s.mu.Unlock()

				s.engine.Enqueue(path)

				if s.bus != nil {
					s.bus.Emit(events.Event{
						Type:   events.EventFileDetected,
						Source: dir,
						Detail: filepath.Base(path),
						Metadata: map[string]string{
							"path": path,
							"size": fmt.Sprintf("%d", info.Size()),
						},
					})
				}

				logger.Infof("Scheduler detected: %s", path)
			}

			return nil
		})
		if err != nil {
			logger.Errorf("Scheduler scan error for %s: %v", dir, err)
		}
	}
}
