# 📂 Directory Organizer

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/release/sparshbajaj/Download-Directory-Organizer.svg)](https://github.com/sparshbajaj/Download-Directory-Organizer/releases)

A smart file organization tool that automatically categorizes your downloads into configurable folders. Inspired by [DropIt](http://dropit.sourceforge.net/), with modern features and cross-platform support.

✨ **Key Features**:
- 🖥️ Modern UI with intuitive controls
- 🔍 Dry-run mode with per-file preview and approval
- 🤖 Local rename intelligence with optional AI provider support
- ⚙️ Persistent settings and configurations
- 📁 Customizable file type mappings with rule editor
- 🛠️ CLI and GUI modes
- 📦 Executable builds for Windows
- 📄 Detailed logging, undo, and error reporting
- 👀 Watch mode for new file arrivals

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
   - Review the rename preview table and approve per file.
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
- **Conflict handling**: Skip, overwrite, append counter, keep both, or move to Conflicts.
- **Filters**: Minimum size, minimum age, and ignored folders.
- **Smart grouping**: Group by date, project, or source app with tagged folders.
- **Undo**: One-click rollback of the last run.

## AI Setup

The default provider is **local** (no network). You can optionally configure a provider compatible with OpenAI's API schema.

### Provider options
- **Local**: Offline SmartRenamer (default)
- **OpenAI**: `https://api.openai.com/v1`
- **OpenRouter**: `https://openrouter.ai/api/v1`
- **Custom**: Provide your own base URL + model

### Configuration fields
- Provider preset
- Base URL
- Model
- API key (masked in UI)
- Temperature, max tokens, timeout
- Consent toggle and “send content snippet” option

### API key sources
API keys can be:
- Entered in the UI (optionally stored in `~/.directory_organizer/settings.json`)
- Provided via environment variables:
  - `OPENAI_API_KEY` for OpenAI
  - `OPENROUTER_API_KEY` for OpenRouter
  - `DIRECTORY_ORGANIZER_AI_KEY` for custom providers

### Data sent & privacy
When consent is enabled, the app sends:
- File name, extension, size
- Optional first 1–2 pages of text content for text files (truncated)

Disable “Send content snippet” to send metadata only, or switch to the Local provider for offline mode.

## Security Notes
- API keys are only stored locally when you enable “Save API key in config.”
- The Local provider never sends data over the network.
- **Save/Load Settings**: Save frequently used configurations for quick access.
- **Customizable**: Easily modify file types and folders in the `config.json` file.
- **Error Handling**: Handles file name conflicts and logs errors.

## Authors

- **Sparsh Bajaj** 
