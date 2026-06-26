// internal/events/events.go
package events

import (
	"database/sql"
	"encoding/json"
	"sync"
	"time"
)

// EventType represents the type of event emitted by the system.
type EventType string

const (
	EventFileDetected   EventType = "file_detected"
	EventFileProcessing EventType = "file_processing"
	EventFileMoved      EventType = "file_moved"
	EventFileError      EventType = "file_error"
	EventWatcherStart   EventType = "watcher_started"
	EventWatcherError   EventType = "watcher_error"
	EventSchedulerTick  EventType = "scheduler_tick"
	EventUpdateAvail    EventType = "update_available"
	EventSystemStart    EventType = "system_start"
	EventHealthCheck    EventType = "health_check"
)

// Event represents a single event in the system.
type Event struct {
	ID        int64             `json:"id"`
	Timestamp time.Time         `json:"timestamp"`
	Type      EventType         `json:"type"`
	Source    string            `json:"source"`
	Detail    string            `json:"detail"`
	Metadata  map[string]string `json:"metadata,omitempty"`
}

// QueryOpts controls filtering when querying events.
type QueryOpts struct {
	Type  EventType
	Since time.Time
	Limit int
}

// Stats holds aggregate statistics about processed files.
type Stats struct {
	TotalProcessed int64 `json:"total_processed"`
	TotalErrors    int64 `json:"total_errors"`
	TodayProcessed int64 `json:"today_processed"`
	TodayErrors    int64 `json:"today_errors"`
	UptimeSeconds  int64 `json:"uptime_seconds"`
}

// Bus is the central event bus with SQLite persistence and in-memory pub/sub.
type Bus struct {
	db          *sql.DB
	subscribers map[int]chan Event
	nextID      int
	mu          sync.RWMutex
	startTime   time.Time
}

// NewBus creates a new event bus backed by the given database.
// It creates the events table if it does not already exist.
func NewBus(db *sql.DB) (*Bus, error) {
	schema := `CREATE TABLE IF NOT EXISTS events (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		timestamp TEXT,
		type TEXT,
		source TEXT,
		detail TEXT,
		metadata TEXT
	);`
	if _, err := db.Exec(schema); err != nil {
		return nil, err
	}
	return &Bus{
		db:          db,
		subscribers: make(map[int]chan Event),
		startTime:   time.Now(),
	}, nil
}

// Emit persists an event to the database and broadcasts it to all subscribers.
func (b *Bus) Emit(evt Event) {
	if evt.Timestamp.IsZero() {
		evt.Timestamp = time.Now()
	}

	// Marshal metadata to JSON
	var metaJSON string
	if evt.Metadata != nil {
		data, err := json.Marshal(evt.Metadata)
		if err == nil {
			metaJSON = string(data)
		}
	}

	// Persist to database
	result, err := b.db.Exec(
		`INSERT INTO events (timestamp, type, source, detail, metadata) VALUES (?, ?, ?, ?, ?)`,
		evt.Timestamp.Format(time.RFC3339), string(evt.Type), evt.Source, evt.Detail, metaJSON,
	)
	if err == nil {
		evt.ID, _ = result.LastInsertId()
	}

	// Broadcast to all subscribers (non-blocking)
	b.mu.RLock()
	defer b.mu.RUnlock()
	for _, ch := range b.subscribers {
		select {
		case ch <- evt:
		default:
			// drop if subscriber is not keeping up
		}
	}
}

// Subscribe returns a channel that receives all future events and an unsubscribe function.
func (b *Bus) Subscribe() (<-chan Event, func()) {
	ch := make(chan Event, 256)

	b.mu.Lock()
	id := b.nextID
	b.nextID++
	b.subscribers[id] = ch
	b.mu.Unlock()

	unsub := func() {
		b.mu.Lock()
		delete(b.subscribers, id)
		b.mu.Unlock()
		close(ch)
	}
	return ch, unsub
}

// Query retrieves events from the database matching the given options.
func (b *Bus) Query(opts QueryOpts) ([]Event, error) {
	query := `SELECT id, timestamp, type, source, detail, metadata FROM events`
	var conditions []string
	var args []interface{}

	if opts.Type != "" {
		conditions = append(conditions, "type = ?")
		args = append(args, string(opts.Type))
	}
	if !opts.Since.IsZero() {
		conditions = append(conditions, "timestamp >= ?")
		args = append(args, opts.Since.Format(time.RFC3339))
	}

	if len(conditions) > 0 {
		query += " WHERE " + conditions[0]
		for i := 1; i < len(conditions); i++ {
			query += " AND " + conditions[i]
		}
	}

	query += " ORDER BY id DESC"

	limit := opts.Limit
	if limit <= 0 {
		limit = 100
	}
	query += " LIMIT ?"
	args = append(args, limit)

	rows, err := b.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []Event
	for rows.Next() {
		var evt Event
		var ts, typ, metaJSON string
		if err := rows.Scan(&evt.ID, &ts, &typ, &evt.Source, &evt.Detail, &metaJSON); err != nil {
			return nil, err
		}
		evt.Type = EventType(typ)
		evt.Timestamp, _ = time.Parse(time.RFC3339, ts)
		if metaJSON != "" {
			json.Unmarshal([]byte(metaJSON), &evt.Metadata)
		}
		events = append(events, evt)
	}
	return events, rows.Err()
}

// Stats returns aggregate statistics about file processing events.
func (b *Bus) Stats() (*Stats, error) {
	s := &Stats{
		UptimeSeconds: int64(time.Since(b.startTime).Seconds()),
	}

	// Total processed (file_moved events)
	row := b.db.QueryRow(`SELECT COUNT(*) FROM events WHERE type = ?`, string(EventFileMoved))
	if err := row.Scan(&s.TotalProcessed); err != nil {
		return nil, err
	}

	// Total errors (file_error events)
	row = b.db.QueryRow(`SELECT COUNT(*) FROM events WHERE type = ?`, string(EventFileError))
	if err := row.Scan(&s.TotalErrors); err != nil {
		return nil, err
	}

	// Today processed
	row = b.db.QueryRow(`SELECT COUNT(*) FROM events WHERE type = ? AND date(timestamp) = date('now')`, string(EventFileMoved))
	if err := row.Scan(&s.TodayProcessed); err != nil {
		return nil, err
	}

	// Today errors
	row = b.db.QueryRow(`SELECT COUNT(*) FROM events WHERE type = ? AND date(timestamp) = date('now')`, string(EventFileError))
	if err := row.Scan(&s.TodayErrors); err != nil {
		return nil, err
	}

	return s, nil
}
