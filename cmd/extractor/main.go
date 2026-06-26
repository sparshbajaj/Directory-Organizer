package main

import (
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type FileInfo struct {
	OriginalFilename string `json:"original_filename"`
	AbsolutePath     string `json:"absolute_path"`
	Extension        string `json:"extension"`
	SizeBytes        int64  `json:"size_bytes"`
	MimeType         string `json:"mime_type"`
	LastModified     string `json:"last_modified"`
	ContentSnippet   string `json:"content_snippet"`
	IsProjectFolder  bool   `json:"is_project_folder"`
}

var projectMarkers = []string{
	".git", "package.json", "go.mod", "pom.xml", "requirements.txt",
	"Makefile", "docker-compose.yml", "docker-compose.yaml",
	"Cargo.toml", "build.gradle", ".sln", ".xcodeproj", "manifest.json",
}

func extractTextSnippet(path string, maxChars int) string {
	ext := strings.ToLower(filepath.Ext(path))
	mimeType := mime.TypeByExtension(ext)
	isText := strings.HasPrefix(mimeType, "text/")

	textExts := map[string]bool{
		".md": true, ".txt": true, ".py": true, ".js": true, ".ts": true,
		".html": true, ".css": true, ".json": true, ".yaml": true, ".yml": true,
		".csv": true, ".go": true, ".rs": true, ".java": true, ".c": true,
		".cpp": true, ".h": true, ".sh": true, ".bat": true, ".ps1": true,
		"": true, // Files without extension like LICENSE, Makefile
	}

	if isText || textExts[ext] {
		file, err := os.Open(path)
		if err != nil {
			return ""
		}
		defer file.Close()

		buf := make([]byte, maxChars)
		n, err := file.Read(buf)
		if err != nil && err != io.EOF {
			return ""
		}

		return strings.TrimSpace(string(buf[:n]))
	}

	return ""
}

func isProjectOrApp(dirPath string) bool {
	entries, err := os.ReadDir(dirPath)
	if err != nil {
		return false
	}

	hasExe := false
	hasDll := false

	for _, entry := range entries {
		name := entry.Name()
		// Check for specific project marker files/folders
		for _, marker := range projectMarkers {
			if strings.EqualFold(name, marker) {
				return true
			}
		}

		// Check for App bundle (.exe + .dll)
		ext := strings.ToLower(filepath.Ext(name))
		if ext == ".exe" {
			hasExe = true
		} else if ext == ".dll" {
			hasDll = true
		}

		if hasExe && hasDll {
			return true
		}
	}
	return false
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println(`{"error": "Directory path required"}`)
		os.Exit(1)
	}

	targetDir := os.Args[1]
	targetDir, err := filepath.Abs(targetDir)
	if err != nil {
		fmt.Printf(`{"error": "Invalid path: %v"}\n`, err)
		os.Exit(1)
	}

	info, err := os.Stat(targetDir)
	if err != nil || !info.IsDir() {
		fmt.Printf(`{"error": "Directory not found or is not a directory: %s"}\n`, targetDir)
		os.Exit(1)
	}

	var results []FileInfo

	err = filepath.WalkDir(targetDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // skip errors
		}

		if path == targetDir {
			return nil // always scan the root directory
		}

		name := d.Name()
		if strings.HasPrefix(name, ".") && name != ".git" {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		if d.IsDir() {
			if isProjectOrApp(path) {
				fileInfo, _ := d.Info()
				// Treat this entire directory as a single unit
				res := FileInfo{
					OriginalFilename: name,
					AbsolutePath:     path,
					Extension:        "",
					SizeBytes:        fileInfo.Size(),
					MimeType:         "directory/project",
					LastModified:     fileInfo.ModTime().Format(time.RFC3339),
					ContentSnippet:   "",
					IsProjectFolder:  true,
				}
				results = append(results, res)
				return filepath.SkipDir
			}
			// Otherwise continue recursing into normal folder
			return nil
		}

		// It's a file
		fileInfo, _ := d.Info()
		ext := strings.ToLower(filepath.Ext(name))
		mimeType := mime.TypeByExtension(ext)
		if mimeType == "" {
			mimeType = "unknown"
		}

		snippet := extractTextSnippet(path, 500)

		res := FileInfo{
			OriginalFilename: name,
			AbsolutePath:     path,
			Extension:        ext,
			SizeBytes:        fileInfo.Size(),
			MimeType:         mimeType,
			LastModified:     fileInfo.ModTime().Format(time.RFC3339),
			ContentSnippet:   snippet,
			IsProjectFolder:  false,
		}
		results = append(results, res)
		return nil
	})

	if err != nil {
		fmt.Printf(`{"error": "Walk error: %v"}\n`, err)
		os.Exit(1)
	}

	jsonData, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		fmt.Printf(`{"error": "Failed to marshal JSON: %v"}\n`, err)
		os.Exit(1)
	}

	fmt.Println(string(jsonData))
}
