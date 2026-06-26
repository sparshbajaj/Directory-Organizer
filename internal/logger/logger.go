// internal/logger/logger.go
package logger

import (
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/sirupsen/logrus"
)

var Log *logrus.Logger
var logFile *os.File

func init() {
	Log = logrus.New()
	Log.SetFormatter(&logrus.TextFormatter{FullTimestamp: true, TimestampFormat: time.RFC3339})
	// Set output to file in %APPDATA%/DirectoryOrganizer/logs/organizer.log
	appData := os.Getenv("APPDATA")
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = home
	}
	logPath := filepath.Join(appData, "DirectoryOrganizer", "logs", "organizer.log")
	if err := os.MkdirAll(filepath.Dir(logPath), 0755); err == nil {
		file, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if err == nil {
			logFile = file
			Log.SetOutput(io.MultiWriter(os.Stdout, file))
		} else {
			Log.SetOutput(os.Stdout)
		}
	} else {
		Log.SetOutput(os.Stdout)
	}
}

// DisableStdout prevents logging to stdout (useful when running TUI)
func DisableStdout() {
	if logFile != nil {
		Log.SetOutput(logFile)
	} else {
		Log.SetOutput(io.Discard)
	}
}

func Infof(format string, args ...interface{}) {
	Log.Infof(format, args...)
}

func Errorf(format string, args ...interface{}) {
	Log.Errorf(format, args...)
}

func Info(args ...interface{}) {
	Log.Info(args...)
}
