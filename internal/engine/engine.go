package engine

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/sparshbajaj/directory-organizer/internal/aiclient"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/knowledge"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/sparshbajaj/directory-organizer/internal/rules"
	_ "modernc.org/sqlite"
)

type Engine struct {
	db        *sql.DB
	cfg       *config.Settings
	aiClient  *aiclient.Client
	rulesEng  *rules.Engine
	kb        *knowledge.DB
	watcher   *fsnotify.Watcher
	workQueue chan string
	stopCh    chan struct{}
	bus       *events.Bus
}

func NewEngine(cfg *config.Settings) (*Engine, error) {
	if err := os.MkdirAll(filepath.Dir(cfg.DBPath), 0755); err != nil {
		return nil, fmt.Errorf("mkdir db dir: %w", err)
	}
	if cfg.WatchDir != "" {
		if err := os.MkdirAll(cfg.WatchDir, 0755); err != nil {
			return nil, fmt.Errorf("mkdir watch dir: %w", err)
		}
	}
	db, err := sql.Open("sqlite", cfg.DBPath)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}
	schema := `
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        original_name TEXT,
        size INTEGER,
        mod_time INTEGER,
        metadata TEXT,
        context TEXT
    );`
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("init schema: %w", err)
	}

	ai, err := aiclient.New(cfg)
	if err != nil {
		return nil, fmt.Errorf("ai client: %w", err)
	}

	rulesEng := rules.New(cfg.RulesPath)
	if err := rulesEng.Load(); err != nil {
		logger.Infof("No existing rules: %v", err)
	}

	var kb *knowledge.DB
	if cfg.KBPath != "" {
		kb, err = knowledge.New(cfg.KBPath)
		if err != nil {
			logger.Infof("No existing knowledge base: %v", err)
		}
	}

	eng := &Engine{
		db:        db,
		cfg:       cfg,
		aiClient:  ai,
		rulesEng:  rulesEng,
		kb:        kb,
		workQueue: make(chan string, 100),
		stopCh:    make(chan struct{}),
	}

	for i := 0; i < 3; i++ {
		go eng.worker()
	}

	return eng, nil
}

func (e *Engine) SetBus(bus *events.Bus) {
	e.bus = bus
}

func (e *Engine) AIClient() *aiclient.Client {
	return e.aiClient
}

func (e *Engine) Rules() *rules.Engine {
	return e.rulesEng
}

func (e *Engine) KB() *knowledge.DB {
	return e.kb
}

func (e *Engine) ScanDirectory() error {
	logger.Infof("Scanning directory %s", e.cfg.WatchDir)
	return filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			logger.Errorf("walk error: %v", err)
			return err
		}
		if info.IsDir() {
			return nil
		}
		return e.upsertFile(p, info.Name(), info.Size(), info.ModTime(), "", "")
	})
}

func (e *Engine) upsertFile(path string, originalName string, size int64, modTime time.Time, metadata string, context string) error {
	stmt := `INSERT INTO files (path, original_name, size, mod_time, metadata, context) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET original_name=excluded.original_name, size=excluded.size, mod_time=excluded.mod_time, metadata=excluded.metadata, context=excluded.context;`
	_, err := e.db.Exec(stmt, path, originalName, size, modTime.Unix(), metadata, context)
	if err != nil {
		logger.Errorf("upsert %s: %v", path, err)
	}
	return err
}

func (e *Engine) RegisterWatcher() error {
	if e.watcher != nil {
		e.watcher.Close()
	}
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	e.watcher = w
	go e.watchLoop()
	return filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return w.Add(p)
		}
		return nil
	})
}

func (e *Engine) OrganizeDirectory() error {
	logger.Infof("Queuing directory %s for organization", e.cfg.WatchDir)
	go func() {
		count := 0
		filepath.Walk(e.cfg.WatchDir, func(p string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if !info.IsDir() {
				e.workQueue <- p
				count++
			}
			return nil
		})
		logger.Infof("Successfully queued %d files for organization.", count)
	}()
	return nil
}

func (e *Engine) BuildKB() {
	if e.kb == nil || e.cfg.WatchDir == "" {
		return
	}
	logger.Info("Building knowledge graph...")
	if err := e.kb.BuildGraph(e.cfg.WatchDir); err != nil {
		logger.Errorf("build kb: %v", err)
	}
	if e.bus != nil {
		count, _ := e.rulesEng.Stats()
		e.bus.Emit(events.Event{
			Type:   events.EventHealthCheck,
			Detail: fmt.Sprintf("Knowledge graph built. Rules: %d", count),
		})
	}
}

func (e *Engine) watchLoop() {
	w := e.watcher
	defer w.Close()
	for {
		select {
		case event, ok := <-w.Events:
			if !ok {
				return
			}
			if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
				e.Enqueue(event.Name)
			}
		case err, ok := <-w.Errors:
			if ok {
				logger.Errorf("watcher error: %v", err)
			}
		}
	}
}

func (e *Engine) Enqueue(path string) {
	select {
	case e.workQueue <- path:
		logger.Infof("Enqueued %s", path)
	default:
		logger.Errorf("Queue full, dropping event for %s", path)
	}
}

func (e *Engine) worker() {
	for {
		select {
		case <-e.stopCh:
			return
		case path := <-e.workQueue:
			e.handleFile(path)
		}
	}
}

func (e *Engine) handleFile(path string) {
	if e.bus != nil {
		e.bus.Emit(events.Event{
			Type:     events.EventFileProcessing,
			Source:   filepath.Dir(path),
			Detail:   fmt.Sprintf("Processing %s", filepath.Base(path)),
			Metadata: map[string]string{"path": path},
		})
	}

	filename := filepath.Base(path)

	if rule := e.rulesEng.Match(filename); rule != nil {
		logger.Infof("Rule matched for %s: %s", filename, rule.Pattern)
		e.applyRule(path, rule)
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Minute*5)
	defer cancel()

	res, err := e.aiClient.Analyze(ctx, path)
	if err != nil {
		logger.Errorf("AI analyze error for %s: %v", path, err)
		if e.bus != nil {
			e.bus.Emit(events.Event{
				Type:     events.EventFileError,
				Source:   filepath.Dir(path),
				Detail:   fmt.Sprintf("AI error for %s: %v", filepath.Base(path), err),
				Metadata: map[string]string{"path": path, "error": err.Error()},
			})
		}
		return
	}
	if res.NewName == "" {
		logger.Infof("AI returned empty name for %s, skipping", path)
		return
	}

	cliName := ""
	if p := e.aiClient.Provider(); p != nil {
		cliName = p.Name()
	}
	e.rulesEng.LearnFromDecision(filename, res.NewName, res.MetadataString(), res.Context, cliName)
	e.rulesEng.Save()

	e.applyResult(path, res)
}

func (e *Engine) applyRule(path string, rule *rules.Rule) {
	originalName := filepath.Base(path)
	dir := filepath.Dir(path)
	ext := filepath.Ext(path)

	newName := rule.NewName
	newName = strings.ReplaceAll(newName, "{{original}}", strings.TrimSuffix(originalName, ext))
	newName = strings.ReplaceAll(newName, "{{ext}}", ext)
	newName = strings.ReplaceAll(newName, "{{date}}", time.Now().Format("2006-01-02"))

	destDir := dir
	if rule.TargetDir != "" {
		destDir = filepath.Join(dir, rule.TargetDir)
		os.MkdirAll(destDir, 0755)
	}
	dest := filepath.Join(destDir, newName+ext)

	if err := os.Rename(path, dest); err != nil {
		logger.Errorf("rule rename %s->%s: %v", path, dest, err)
		return
	}
	logger.Infof("Rule applied: %s -> %s", path, dest)

	if e.bus != nil {
		e.bus.Emit(events.Event{
			Type:   events.EventFileMoved,
			Source: dir,
			Detail: fmt.Sprintf("%s -> %s (rule)", originalName, newName+ext),
		})
	}

	e.updateKB(dest, originalName, rule.Metadata, rule.Context)
}

func (e *Engine) applyResult(path string, res *aiclient.AIResult) {
	originalName := filepath.Base(path)
	dir := filepath.Dir(path)
	ext := filepath.Ext(path)
	dest := filepath.Join(dir, res.NewName+ext)

	if err := os.Rename(path, dest); err != nil {
		logger.Errorf("rename %s->%s failed: %v", path, dest, err)
		if e.bus != nil {
			e.bus.Emit(events.Event{
				Type:     events.EventFileError,
				Source:   dir,
				Detail:   fmt.Sprintf("Rename failed: %s -> %s: %v", originalName, res.NewName+ext, err),
				Metadata: map[string]string{"path": path, "error": err.Error()},
			})
		}
		return
	}
	logger.Infof("Renamed %s to %s", path, dest)

	if e.bus != nil {
		e.bus.Emit(events.Event{
			Type:   events.EventFileMoved,
			Source: dir,
			Detail: fmt.Sprintf("%s -> %s", originalName, res.NewName+ext),
			Metadata: map[string]string{
				"original_path": path,
				"new_path":      dest,
				"new_name":      res.NewName + ext,
				"original_name": originalName,
			},
		})
	}

	info, err := os.Stat(dest)
	if err == nil {
		e.upsertFile(dest, originalName, info.Size(), info.ModTime(), res.MetadataString(), res.Context)
	}

	e.updateKB(dest, originalName, res.MetadataString(), res.Context)

	if e.cfg.VaultPath != "" {
		os.MkdirAll(e.cfg.VaultPath, 0755)
		vContent := fmt.Sprintf("# %s\n\n**Original Path:** %s\n**Date Organized:** %s\n**Metadata:** %s\n\n## Context\n%s",
			res.NewName, path, time.Now().Format("2006-01-02"), res.MetadataString(), res.Context)
		os.WriteFile(filepath.Join(e.cfg.VaultPath, res.NewName+".md"), []byte(vContent), 0644)
	}
}

func (e *Engine) updateKB(path, originalName, metadata, context string) {
	if e.kb == nil {
		return
	}
	info, err := os.Stat(path)
	if err != nil {
		return
	}
	tags := []string{}
	if metadata != "" {
		for _, t := range strings.Split(metadata, ",") {
			tags = append(tags, strings.TrimSpace(t))
		}
	}
	e.kb.UpsertContext(path, context, metadata, originalName, info.Size(), info.ModTime(), tags)
}

func (e *Engine) Close() error {
	if e.stopCh != nil {
		close(e.stopCh)
	}
	if e.watcher != nil {
		e.watcher.Close()
	}
	if e.kb != nil {
		e.kb.Close()
	}
	return e.db.Close()
}
