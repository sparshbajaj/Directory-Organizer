// internal/dashboard/server.go
package dashboard

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/sparshbajaj/directory-organizer/internal/aiclient"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/events"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/sparshbajaj/directory-organizer/internal/updater"
)

//go:embed static/*
var staticFiles embed.FS

// Server hosts the dashboard web UI and its API endpoints.
type Server struct {
	bus      *events.Bus
	updater  *updater.Updater
	cfg      *config.Settings
	aiClient *aiclient.Client
	version  string
	port     int
	start    time.Time
}

// NewServer creates a dashboard server wired to the event bus, updater, and
// application settings.
func NewServer(bus *events.Bus, upd *updater.Updater, ai *aiclient.Client, cfg *config.Settings, version string) *Server {
	return &Server{
		bus:      bus,
		updater:  upd,
		aiClient: ai,
		cfg:      cfg,
		version:  version,
		start:    time.Now(),
	}
}

// Start binds the HTTP server to the given port and blocks until ctx is
// cancelled. On context cancellation the server is gracefully shut down.
func (s *Server) Start(ctx context.Context, port int) error {
	s.port = port
	mux := http.NewServeMux()

	// API routes
	mux.HandleFunc("/api/status", s.handleStatus)
	mux.HandleFunc("/api/events", s.handleEvents)
	mux.HandleFunc("/api/events/stream", s.handleSSE)
	mux.HandleFunc("/api/stats", s.handleStats)
	mux.HandleFunc("/api/dirs", s.handleDirs)
	mux.HandleFunc("/api/update", s.handleUpdate)
	mux.HandleFunc("/api/analyze", s.handleAnalyze)
	mux.HandleFunc("/api/event", s.handleEventPost)

	// Static files – the embedded FS has the shape static/*, so we strip the
	// leading "static" prefix to serve from "/".
	staticFS, err := fs.Sub(staticFiles, "static")
	if err != nil {
		return fmt.Errorf("dashboard: failed to open embedded static FS: %w", err)
	}
	mux.Handle("/", http.FileServer(http.FS(staticFS)))

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", port),
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			logger.Errorf("Dashboard shutdown error: %v", err)
		}
	}()

	logger.Infof("Dashboard listening on :%d", port)
	return srv.ListenAndServe()
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// writeJSON serialises data as JSON and writes it with CORS headers.
func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data) //nolint:errcheck
}

// formatUptime returns a human-readable duration string (e.g. "3h 25m 45s").
func formatUptime(d time.Duration) string {
	h := int(d.Hours())
	m := int(d.Minutes()) % 60
	sec := int(d.Seconds()) % 60
	if h > 0 {
		return fmt.Sprintf("%dh %dm %ds", h, m, sec)
	}
	if m > 0 {
		return fmt.Sprintf("%dm %ds", m, sec)
	}
	return fmt.Sprintf("%ds", sec)
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

// handleStatus responds with the daemon's current runtime status.
func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}

	uptime := time.Since(s.start)

	dirs := s.cfg.WatchDirs
	if dirs == nil {
		dirs = []string{}
		// Fallback: if the older single-dir field is populated, use it.
		if s.cfg.WatchDir != "" {
			dirs = []string{s.cfg.WatchDir}
		}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status":         "running",
		"version":        s.version,
		"uptime_seconds": int(uptime.Seconds()),
		"uptime_human":   formatUptime(uptime),
		"mode":           s.cfg.Mode,
		"directories":    dirs,
		"port":           s.port,
	})
}

// handleEvents returns a filtered, paginated list of recent events.
//
// Query parameters:
//
//	type  – filter by event type (optional)
//	since – RFC 3339 timestamp lower bound (optional)
//	limit – maximum number of results (default 100)
func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}

	q := r.URL.Query()

	eventType := q.Get("type")

	var since time.Time
	if raw := q.Get("since"); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "invalid 'since' parameter – expected RFC 3339",
			})
			return
		}
		since = parsed
	}

	limit := 100
	if raw := q.Get("limit"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n < 1 {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "invalid 'limit' parameter – expected positive integer",
			})
			return
		}
		limit = n
	}

	results, err := s.bus.Query(events.QueryOpts{
		Type:  events.EventType(eventType),
		Since: since,
		Limit: limit,
	})
	if err != nil || results == nil {
		results = []events.Event{}
	}

	writeJSON(w, http.StatusOK, results)
}

// handleSSE streams events to the client via Server-Sent Events.
func (s *Server) handleSSE(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "SSE not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	ch, unsub := s.bus.Subscribe()
	defer unsub()

	ctx := r.Context()
	for {
		select {
		case <-ctx.Done():
			return
		case evt, ok := <-ch:
			if !ok {
				return
			}
			data, err := json.Marshal(evt)
			if err != nil {
				logger.Errorf("SSE marshal error: %v", err)
				continue
			}
			fmt.Fprintf(w, "data: %s\n\n", data)
			flusher.Flush()
		}
	}
}

// handleStats returns aggregate event statistics.
func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}
	stats, err := s.bus.Stats()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

// dirInfo describes one monitored directory for the /api/dirs endpoint.
type dirInfo struct {
	Path      string `json:"path"`
	Mode      string `json:"mode"`
	Exists    bool   `json:"exists"`
	FileCount int    `json:"file_count"`
}

// handleDirs returns metadata about each monitored directory.
func (s *Server) handleDirs(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}

	dirs := s.cfg.WatchDirs
	if dirs == nil || len(dirs) == 0 {
		// Fallback for single-directory config.
		if s.cfg.WatchDir != "" {
			dirs = []string{s.cfg.WatchDir}
		}
	}

	mode := s.cfg.Mode
	if mode == "" {
		mode = "watch"
	}

	infos := make([]dirInfo, 0, len(dirs))
	for _, d := range dirs {
		info := dirInfo{
			Path: d,
			Mode: mode,
		}

		fi, err := os.Stat(d)
		if err == nil && fi.IsDir() {
			info.Exists = true
			count := 0
			filepath.Walk(d, func(path string, wfi os.FileInfo, err error) error { //nolint:errcheck
				if err != nil {
					return nil // skip unreadable entries
				}
				if !wfi.IsDir() {
					count++
				}
				return nil
			})
			info.FileCount = count
		}

		infos = append(infos, info)
	}

	writeJSON(w, http.StatusOK, infos)
}

// handleUpdate checks for a newer release and reports availability.
func (s *Server) handleUpdate(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}

	if s.updater == nil {
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"current_version": s.version,
			"has_update":      false,
			"error":           "updater disabled",
		})
		return
	}

	hasUpdate := s.updater.HasUpdate()
	release := s.updater.Latest()

	resp := map[string]interface{}{
		"current_version": s.version,
		"has_update":      hasUpdate,
	}
	if hasUpdate && release != nil {
		resp["latest"] = release
	}
	writeJSON(w, http.StatusOK, resp)
}

// handleAnalyze accepts a file upload, analyzes it using the AI client, and returns the result.
func (s *Server) handleAnalyze(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	// Parse multipart form (max 10MB memory)
	if err := r.ParseMultipartForm(10 << 20); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "failed to parse multipart form"})
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing 'file' in form data"})
		return
	}
	defer file.Close()

	// Create temp file
	tmpDir := os.TempDir()
	tmpPath := filepath.Join(tmpDir, "vaultsort_upload_"+header.Filename)
	out, err := os.Create(tmpPath)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to create temp file"})
		return
	}
	
	if _, err := io.Copy(out, file); err != nil {
		out.Close()
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to write temp file"})
		return
	}
	out.Close()
	defer os.Remove(tmpPath) // Cleanup

	if s.aiClient == nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "AI client not configured"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()
	
	res, err := s.aiClient.Analyze(ctx, tmpPath)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, res)
}

// handleEventPost allows remote clients to emit events to the central dashboard.
func (s *Server) handleEventPost(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		writeJSON(w, http.StatusNoContent, nil)
		return
	}
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	var evt events.Event
	if err := json.NewDecoder(r.Body).Decode(&evt); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json payload"})
		return
	}
	
	if evt.Timestamp.IsZero() {
		evt.Timestamp = time.Now()
	}

	if s.bus != nil {
		s.bus.Emit(evt)
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
