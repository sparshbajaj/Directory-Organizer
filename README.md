# 📂 Directory Organizer

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/release/sparshbajaj/Download-Directory-Organizer.svg)](https://github.com/sparshbajaj/Download-Directory-Organizer/releases)

A smart file organization tool that automatically categorizes your downloads into configurable folders. Inspired by [DropIt](http://dropit.sourceforge.net/), with modern features and cross-platform support.

✨ **Key Features**:
- 🖥️ Modern UI with intuitive controls
- 🔍 Dry-run mode to preview changes
- 🤖 AI-inspired renaming based on file context
- ⚙️ Persistent settings and configurations
- 📁 Customizable file type mappings
- 🛠️ CLI and GUI modes
- 📦 Executable builds for Windows
- 📄 Detailed logging and error handling

## Getting Started

### Using the UI

1. Clone or download the project.
2. Run the following command to start the UI:
   ```
   python3 ui.py
   ```
3. Use the UI to:
   - Select the source directory (e.g., your Downloads folder).
   - Select a configuration file (e.g., `config.json`) to define file types and their corresponding folders.
   - Preview changes to see what files will be moved.
   - Optionally enable AI rename to generate cleaner filenames.
   - Organize files into folders based on their types.
   - Save and load settings for future use.

### Using the Command Line

1. Run the script directly:
   ```
   python3 Cleaner\ 2.0/cleaner.py --directory <path_to_directory> --config <path_to_config.json>
   ```
2. Use additional arguments:
   - `--dry-run`: Preview changes without moving files (generates preview_changes.txt)
   - `--log <path_to_log_file>`: Save logs to a file
   - `--preview`: Alias for --dry-run

### Configuration

The `config.json` file defines the file types and their corresponding folders. You can customize it to add or modify file types. Example:
```json
{
  "Videos": [".mp4", ".mkv", ".avi"],
  "Pictures": [".jpg", ".png", ".gif"],
  "Documents": [".pdf", ".docx", ".txt"]
}
```

### Prerequisites

- Python 3.x
- `tkinter` (for the UI)

Install `tkinter` on Linux if not already installed:
```bash
sudo apt-get install python3-tk
```

## Building from Source

1. Install required packages:
   ```bash
   pip install pyinstaller
   ```
2. Build executable:
   ```bash
   python build.py
   ```
3. Find the executable in `dist/DownloadOrganizer.exe`

## Releases

Pre-built Windows executables are available in [GitHub Releases](https://github.com/yourusername/Download-Directory-Organizer/releases).

### Using the Executable

- **GUI Mode**: Double-click `DownloadOrganizer.exe`
- **Command Line**:
  ```bash
  DownloadOrganizer.exe --directory <path> --config <config.json>
  ```
  Options:
  - `--preview`: Generate preview_changes.txt without moving files
  - `--dry-run`: Same as --preview
  - `--log <path>`: Save operation logs to file

## Features

- **UI**: A modern and minimal interface for organizing files.
- **Preview Changes**: Generates `preview_changes.txt` showing planned moves and creates folders
- **AI Rename**: Generates cleaner names using file context for text-based files and metadata.
- **Save/Load Settings**: Save frequently used configurations for quick access.
- **Customizable**: Easily modify file types and folders in the `config.json` file.
- **Error Handling**: Handles file name conflicts and logs errors.

## Authors

- **Sparsh Bajaj** 
