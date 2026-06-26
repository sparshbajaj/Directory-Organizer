package rules

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type Rule struct {
	ID           string  `json:"id"`
	Pattern      string  `json:"pattern"`
	NewName      string  `json:"new_name"`   // template, can include {{ext}} {{date}} etc.
	TargetDir    string  `json:"target_dir"` // subdirectory to move into, "" = same dir
	Metadata     string  `json:"metadata"`
	Context      string  `json:"context"`
	SourceCLI    string  `json:"source_cli"` // which CLI created it
	Confidence   float64 `json:"confidence"`
	TimesApplied int     `json:"times_applied"`
	CreatedAt    int64   `json:"created_at"`
	UpdatedAt    int64   `json:"updated_at"`
}

type Engine struct {
	mu    sync.RWMutex
	Rules []Rule `json:"rules"`
	path  string
}

func New(path string) *Engine {
	return &Engine{path: path}
}

func (e *Engine) Load() error {
	e.mu.Lock()
	defer e.mu.Unlock()
	data, err := os.ReadFile(e.path)
	if err != nil {
		if os.IsNotExist(err) {
			e.Rules = nil
			return nil
		}
		return err
	}
	return json.Unmarshal(data, &e.Rules)
}

func (e *Engine) Save() error {
	e.mu.RLock()
	defer e.mu.RUnlock()
	if err := os.MkdirAll(filepath.Dir(e.path), 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(e.Rules, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(e.path, data, 0644)
}

func (e *Engine) Match(filename string) *Rule {
	e.mu.RLock()
	defer e.mu.RUnlock()
	for i := range e.Rules {
		r := &e.Rules[i]
		if matched, _ := filepath.Match(r.Pattern, filename); matched {
			return r
		}
		if strings.Contains(filename, r.Pattern) {
			return r
		}
	}
	return nil
}

func (e *Engine) AddOrUpdate(r Rule) {
	e.mu.Lock()
	defer e.mu.Unlock()
	for i := range e.Rules {
		if e.Rules[i].Pattern == r.Pattern {
			e.Rules[i].Confidence = (e.Rules[i].Confidence*float64(e.Rules[i].TimesApplied) + r.Confidence) / float64(e.Rules[i].TimesApplied+1)
			e.Rules[i].TimesApplied++
			e.Rules[i].UpdatedAt = time.Now().Unix()
			e.Rules[i].NewName = r.NewName
			e.Rules[i].TargetDir = r.TargetDir
			e.Rules[i].Metadata = r.Metadata
			e.Rules[i].Context = r.Context
			return
		}
	}
	r.ID = "rule-" + time.Now().Format("150405.000000")
	r.CreatedAt = time.Now().Unix()
	r.UpdatedAt = r.CreatedAt
	r.TimesApplied = 1
	e.Rules = append(e.Rules, r)
}

func (e *Engine) LearnFromDecision(filename, newName, metadata, context, cliName string) {
	e.AddOrUpdate(Rule{
		Pattern:    "*.txt", // ponytail: starts from extension, upgrades via self-improvement
		NewName:    newName,
		Metadata:   metadata,
		Context:    context,
		SourceCLI:  cliName,
		Confidence: 0.5,
	})
}

func (e *Engine) Stats() (count int, avgConf float64) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	count = len(e.Rules)
	if count == 0 {
		return 0, 0
	}
	var sum float64
	for _, r := range e.Rules {
		sum += r.Confidence
	}
	return count, sum / float64(count)
}
