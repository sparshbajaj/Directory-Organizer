# 📂 Directory Organizer (TUI Revamp)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A smart, terminal-first, AI-native file organization tool that automatically scans, renames, and categorizes downloads into custom folders. Powered by a Textual TUI frontend, SQLite backend, and flexible AI models (including local command-line tools like Gemini CLI and Claude Code).

---

## ✨ Key Features

- 🖥️ **Modern TUI**: Fully keyboard-driven terminal user interface built with the [Textual](https://textual.textualize.io/) framework.
- 🤖 **AI-Native Renaming**: Context-aware suggested names using direct API endpoints (OpenAI, OpenRouter, Custom) or local command-line agents (`gemini-cli`, `claude-cli`).
- 🔍 **First-Time Wizard**: Initial setup flow to guide you through AI providers, models, endpoints, and credentials.
- 📦 **Text Extraction**: Auto-parses document content (`.pdf`, `.docx`, `.pptx`, `.txt`) to supply text context directly to the AI model.
- 🗄️ **SQLite DB Audit Log**: Tracks full execution histories, individual suggestions, and atomic file move logs.
- 🛠️ **Perfect Undo**: Interactive run history browser with one-key rollback (`U`) to restore files to their exact original paths and names.
- 🌳 **Unicode Graph Map**: Interactive folder cluster tree representing categories, folder layouts, and planned changes.
- ⚡ **Performance Controls**: Adjustable timeouts, request batching pauses, and a **Test Scan Limit** to restrict traversal on large directories.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A configured terminal with 256-color support (recommended).

### Installation

1. Clone or download the repository.
2. Create and activate a virtual environment, then install the dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # On Windows
   source .venv/bin/activate # On Unix/macOS
   pip install -r requirements.txt
   ```

### Launching the Terminal UI

Run the TUI app entry point:
```bash
python tui.py
```
On your first launch, you will be prompted with the **First-Time Config Wizard** to set up your AI options.

#### Key Bindings in suggestions Screen:
*   `Space`: Toggle/Approve suggestion.
*   `E`: Edit proposed filename.
*   `Y`: Apply approved changes.
*   `M`: View folder relationship map.
*   `Q` / `Esc`: Back to configuration screen.

#### Key Bindings in History Screen:
*   `U`: Roll back/Undo the selected run.
*   `Q` / `Esc`: Back to main config screen.

---

## 💻 CLI Usage

Execute the background organizer engine directly from your terminal:
```bash
python cleaner.py --directory <path> --config <path_to_config.json>
```

### Options:
- `--dry-run` / `--preview`: Perform a simulated run and export planned changes to `preview_changes.txt` without moving files.
- `--log <path>`: Output logs to a custom file.
- `--ai-provider <provider>`: Force a specific AI provider (e.g. `openai`, `gemini-cli`).
- `--scan-limit <int>`: Restrict scanning to at most `N` files (useful for quick tests).

---

## 🛠️ Configuration

File types are categorized using `config.json`. Customize this file to add or modify folders and extension mappings:
```json
{
  "Videos": [".mp4", ".mkv", ".avi"],
  "Pictures": [".jpg", ".png", ".gif"],
  "Books": [".pdf", ".epub"],
  "Documents": [".docx", ".doc", ".txt"]
}
```

---

## 🤖 AI Provider Setup

### 1. Direct API Providers
- **OpenAI**: Requires `api_key` and uses standard endpoints.
- **OpenRouter**: Useful for routing prompts to open-source models.
- **Custom**: Specify any OpenAI-compatible base URL and model name.

*Note: Keys can be entered in the UI or set via environment variables (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or `DIRECTORY_ORGANIZER_AI_KEY`).*

### 2. Local CLI Providers
- **Gemini CLI (`gemini-cli`)**: Uses your local `@google/gemini-cli` installation (configured via your local terminal session).
- **Claude Code CLI (`claude-cli`)**: Uses your local `@anthropic-ai/claude-code` installation.

On Windows, the application automatically handles NPM global batch file wrappers (`.cmd` wrappers) and optimizes command timeouts to 90 seconds to prevent execution bottlenecks. It also sanitizes prompt strings to prevent command truncation in `cmd.exe`.

---

## 🔒 Privacy & Security

- **Local Processing**: When using the **Local** provider preset or when consent is disabled, no data is sent over the network.
- **Snippet Consent**: When "Consent to send snippet" is enabled, text extraction is limited to supported extensions. Binary payloads are never sent.
- **Credential Storage**: Settings and masked API keys are saved strictly locally in `~/.directory_organizer/settings.json`.

---

## 🗺️ Future Roadmap & TODOs

- [ ] **HTML Map Export**: Post-MVP option to export the relationship tree and category clusters to an interactive web-based HTML graph using `pyvis`.
- [ ] **Daemon Watcher Mode**: Background daemon task to watch directories for automatic folder allocation using the SQLite database cache.
- [ ] **Advanced File Deduplication**: Auto-detect content duplicates based on file hashes during TUI scan runs.

---

## ✍️ Authors

- **Sparsh Bajaj**
