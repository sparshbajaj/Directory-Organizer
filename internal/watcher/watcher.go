// internal/watcher/watcher.go
package watcher

import (
	"fmt"
	"github.com/fsnotify/fsnotify"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"os"
	"path/filepath"
	"strings"
)

// Watcher watches a directory recursively and notifies the engine of file events.
type Watcher struct {
	watcher *fsnotify.Watcher
	engine  *engine.Engine
	roots   []string
}

// New creates a new Watcher linked to the given engine.
func New(e *engine.Engine) (*Watcher, error) {
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, err
	}
	return &Watcher{watcher: w, engine: e}, nil
}

// AddPath adds a path (file or directory) to be watched. Directories are added recursively.
func (w *Watcher) AddPath(p string) error {
	info, err := os.Stat(p)
	if err != nil {
		return err
	}
	if info.IsDir() {
		// walk recursively
		return filepath.Walk(p, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if info.IsDir() {
				// skip hidden folders if desired
				if strings.HasPrefix(info.Name(), ".") {
					return filepath.SkipDir
				}
				return w.watcher.Add(path)
			}
			return nil
		})
	}
	// single file
	return w.watcher.Add(p)
}

// Run starts the event loop. It should be called in a goroutine.
func (w *Watcher) Run(stopCh <-chan struct{}) {
	defer w.watcher.Close()
	for {
		select {
		case <-stopCh:
			logger.Info("watcher stopping")
			return
		case event, ok := <-w.watcher.Events:
			if !ok {
				return
			}
			// We're interested in create/write events
			if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
				logger.Infof("file changed, enqueuing: %s", event.Name)
				w.engine.Enqueue(event.Name)
			}
		case err, ok := <-w.watcher.Errors:
			if !ok {
				return
			}
			logger.Errorf("watcher error: %v", err)
		}
	}
}

// Helper to start watching multiple roots.
func (w *Watcher) AddRoots(paths []string) error {
	for _, p := range paths {
		if err := w.AddPath(p); err != nil {
			return fmt.Errorf("add watch %s: %w", p, err)
		}
		w.roots = append(w.roots, p)
	}
	return nil
}
