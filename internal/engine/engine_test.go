// internal/engine/engine_test.go
package engine

import (
    "os"
    "path/filepath"
    "testing"
    
    "github.com/sparshbajaj/directory-organizer/internal/config"
    "github.com/stretchr/testify/assert"
)

func TestEngine_ScanDirectory(t *testing.T) {
    // Setup temporary APPDATA directory to isolate DB
    appDataDir, err := os.MkdirTemp("", "appdata_test")
    assert.NoError(t, err)
    defer os.RemoveAll(appDataDir)
    os.Setenv("APPDATA", appDataDir)

    // Create temporary directory to scan
    scanDir, err := os.MkdirTemp("", "scan_test")
    assert.NoError(t, err)
    defer os.RemoveAll(scanDir)

    // Create a test file
    filePath := filepath.Join(scanDir, "test.txt")
    err = os.WriteFile(filePath, []byte("hello world"), 0644)
    assert.NoError(t, err)

    // Create a mock config
    cfg := &config.Settings{
        DBPath:   filepath.Join(appDataDir, "test.db"),
        WatchDir: scanDir,
        BaseURL:  "http://localhost",
    }

    eng, err := NewEngine(cfg)
    assert.NoError(t, err)
    defer eng.Close()

    // Perform scan
    err = eng.ScanDirectory()
    assert.NoError(t, err)

    // Verify that the file was indexed in SQLite DB
    var count int
    row := eng.db.QueryRow("SELECT COUNT(*) FROM files WHERE path = ?", filePath)
    err = row.Scan(&count)
    assert.NoError(t, err)
    assert.Equal(t, 1, count, "file should be present in index")
}
