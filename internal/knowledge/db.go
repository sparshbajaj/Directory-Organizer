package knowledge

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type DB struct {
	db *sql.DB
}

type FileContext struct {
	Path         string   `json:"path"`
	Context      string   `json:"context"`
	Tags         []string `json:"tags"`
	RelatedFiles []string `json:"related_files"`
	Metadata     string   `json:"metadata"`
	OriginalName string   `json:"original_name"`
	Size         int64    `json:"size"`
	ModTime      int64    `json:"mod_time"`
}

func New(path string) (*DB, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return nil, fmt.Errorf("mkdir kb: %w", err)
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open kb: %w", err)
	}
	schema := `
	CREATE TABLE IF NOT EXISTS file_contexts (
		path TEXT PRIMARY KEY,
		context TEXT,
		tags TEXT,
		metadata TEXT,
		original_name TEXT,
		size INTEGER,
		mod_time INTEGER,
		created_at INTEGER,
		updated_at INTEGER
	);
	CREATE TABLE IF NOT EXISTS file_relationships (
		source_path TEXT,
		target_path TEXT,
		relationship_type TEXT,
		strength REAL,
		created_at INTEGER,
		PRIMARY KEY (source_path, target_path, relationship_type)
	);
	CREATE INDEX IF NOT EXISTS idx_rel_target ON file_relationships(target_path);
	CREATE INDEX IF NOT EXISTS idx_rel_type ON file_relationships(relationship_type);`
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("init kb schema: %w", err)
	}
	return &DB{db: db}, nil
}

func (k *DB) UpsertContext(path, context, metadata, originalName string, size int64, modTime time.Time, tags []string) error {
	tagStr := strings.Join(tags, ",")
	now := time.Now().Unix()
	_, err := k.db.Exec(`INSERT INTO file_contexts (path, context, tags, metadata, original_name, size, mod_time, created_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(path) DO UPDATE SET context=excluded.context, tags=excluded.tags, metadata=excluded.metadata,
		original_name=excluded.original_name, size=excluded.size, mod_time=excluded.mod_time, updated_at=excluded.updated_at`,
		path, context, tagStr, metadata, originalName, size, modTime.Unix(), now, now)
	return err
}

func (k *DB) AddRelationship(source, target, relType string, strength float64) error {
	_, err := k.db.Exec(`INSERT OR REPLACE INTO file_relationships (source_path, target_path, relationship_type, strength, created_at)
		VALUES (?, ?, ?, ?, ?)`, source, target, relType, strength, time.Now().Unix())
	return err
}

func (k *DB) GetContext(path string) (*FileContext, error) {
	row := k.db.QueryRow(`SELECT path, context, tags, metadata, original_name, size, mod_time FROM file_contexts WHERE path=?`, path)
	var fc FileContext
	var tagStr string
	if err := row.Scan(&fc.Path, &fc.Context, &tagStr, &fc.Metadata, &fc.OriginalName, &fc.Size, &fc.ModTime); err != nil {
		return nil, err
	}
	if tagStr != "" {
		fc.Tags = strings.Split(tagStr, ",")
	}
	fc.RelatedFiles = k.getRelated(fc.Path)
	return &fc, nil
}

func (k *DB) getRelated(path string) []string {
	rows, err := k.db.Query(`SELECT target_path FROM file_relationships WHERE source_path=? ORDER BY strength DESC LIMIT 20`, path)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var paths []string
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err == nil {
			paths = append(paths, p)
		}
	}
	return paths
}

func (k *DB) GetRelatedGraph(path string) (map[string]interface{}, error) {
	fc, err := k.GetContext(path)
	if err != nil {
		return nil, err
	}
	related := make([]map[string]interface{}, 0)
	for _, rp := range fc.RelatedFiles {
		rc, err := k.GetContext(rp)
		if err != nil {
			continue
		}
		related = append(related, map[string]interface{}{
			"path":    rc.Path,
			"context": rc.Context,
			"tags":    rc.Tags,
		})
	}
	return map[string]interface{}{
		"file":    fc,
		"related": related,
	}, nil
}

func (k *DB) BuildGraph(dir string) error {
	filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		fc, err := k.GetContext(path)
		if err != nil {
			return nil
		}
		filepath.Walk(dir, func(path2 string, info2 os.FileInfo, err2 error) error {
			if err2 != nil || info2.IsDir() || path == path2 {
				return nil
			}
			fc2, err2 := k.GetContext(path2)
			if err2 != nil {
				return nil
			}
			if fc.Context != "" && fc2.Context != "" && wordsOverlap(fc.Context, fc2.Context) {
				k.AddRelationship(path, path2, "context_overlap", 0.5)
			}
			if tagsOverlap(fc.Tags, fc2.Tags) {
				k.AddRelationship(path, path2, "shared_tags", 0.7)
			}
			return nil
		})
		return nil
	})
	return nil
}

func (k *DB) AllContexts() ([]*FileContext, error) {
	rows, err := k.db.Query(`SELECT path, context, tags, metadata, original_name, size, mod_time FROM file_contexts ORDER BY mod_time DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var result []*FileContext
	for rows.Next() {
		var fc FileContext
		var tagStr string
		if err := rows.Scan(&fc.Path, &fc.Context, &tagStr, &fc.Metadata, &fc.OriginalName, &fc.Size, &fc.ModTime); err != nil {
			continue
		}
		if tagStr != "" {
			fc.Tags = strings.Split(tagStr, ",")
		}
		fc.RelatedFiles = k.getRelated(fc.Path)
		result = append(result, &fc)
	}
	return result, nil
}

func (k *DB) Close() error {
	return k.db.Close()
}

func wordsOverlap(a, b string) bool {
	wordsA := strings.Fields(strings.ToLower(a))
	wordsB := strings.Fields(strings.ToLower(b))
	for _, wa := range wordsA {
		if len(wa) < 4 {
			continue
		}
		for _, wb := range wordsB {
			if wa == wb {
				return true
			}
		}
	}
	return false
}

func tagsOverlap(a, b []string) bool {
	for _, ta := range a {
		for _, tb := range b {
			if ta == tb {
				return true
			}
		}
	}
	return false
}

func (k *DB) ExportGraphJSON() (string, error) {
	contexts, err := k.AllContexts()
	if err != nil {
		return "", err
	}
	type node struct {
		ID    string   `json:"id"`
		Label string   `json:"label"`
		Tags  []string `json:"tags"`
	}
	type edge struct {
		Source string `json:"source"`
		Target string `json:"target"`
		Type   string `json:"type"`
	}
	var nodes []node
	var edges []edge
	seen := map[string]bool{}
	for _, fc := range contexts {
		nodes = append(nodes, node{
			ID:    fc.Path,
			Label: filepath.Base(fc.Path),
			Tags:  fc.Tags,
		})
		seen[fc.Path] = true
		for _, rel := range fc.RelatedFiles {
			if seen[rel] {
				edges = append(edges, edge{Source: fc.Path, Target: rel, Type: "related"})
			}
		}
	}
	graph := map[string]interface{}{
		"nodes": nodes,
		"edges": edges,
	}
	data, _ := json.MarshalIndent(graph, "", "  ")
	return string(data), nil
}
