# 📂 VaultSort: AI-Powered Directory Organizer & Obsidian Vault

[![Go Version](https://img.shields.io/badge/Go-1.20+-00ADD8.svg)](https://golang.org/)
[![AI Powered](https://img.shields.io/badge/AI-Native-blueviolet.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Welcome to **VaultSort** (formerly Directory Organizer 3.0), the ultimate auto-evolving file manager and desktop service. VaultSort has been completely overhauled from a standalone Python script into a native, high-performance **Antigravity Agent Skill** powered by Go.

Instead of relying on rigid rules and manual regular expressions, VaultSort integrates directly with your terminal's AI agent. It uses a lightning-fast Go extractor to safely read file contents and metadata, and leverages the **Antigravity CLI (`agy`)** to intelligently suggest filenames, categorize documents, and build a highly searchable **Obsidian-style Markdown Vault** of your entire digital life.

---

## ✨ Key Features

- 🤖 **Native Antigravity Integration**: Run the agent skill directly using the `agy` CLI to intelligently organize files based on their actual content.
- 💻 **Zero-Config Terminal UI**: An interactive, user-friendly Terminal UI with an **auto-starting background watcher**. Perfect for non-technical users—just open the app, and it immediately starts monitoring and organizing your target folder.
- ⚡ **Go-Powered Context Extractor**: A zero-dependency scanner (`cmd/extractor/main.go`) that parses files while strictly respecting **Project Boundaries** (detecting `.git`, `node_modules`, Cargo, etc.) to keep your active coding projects intact.
- 📓 **Obsidian-Style Markdown Vault**: Generates a clean, plain-text knowledge base of all your organized files inside a `vault/` directory. Each note logs the original path, context, and a text snippet, transforming your filesystem into a searchable database.
- 🧬 **Self-Modifying Auto-Evolution**: The agent autonomously updates the Go extractor source code (e.g., adding support for new text extensions) and refines its own `SKILL.md` rules as it discovers new file types.

---

## 🚀 Quick Start

Follow these simple steps to get your files organized:

### 1. Prerequisites
- **[Go (Golang) 1.20+](https://golang.org/dl/)** installed on your system.
- The **Antigravity CLI (`agy` command)** installed and configured in your shell.

### 2. Build the Project
Compile the VaultSort executable:
```bash
go build -o organizer.exe main.go
```

### 3. Launch the TUI (Terminal UI)
For the easiest experience, launch the TUI. It starts monitoring in the background immediately:
```bash
./organizer.exe tui
```

---

## 🖥️ Using the Terminal UI (TUI)

The TUI is built using [Bubble Tea](https://github.com/charmbracelet/bubbletea) and is designed for zero friction.

> [!TIP]
> **No configuration required!** As soon as you open the TUI, it automatically boots up a background watcher on your target folder. Any files dropped into that folder will be immediately processed by the AI engine.

### TUI Menu Options:
1. **`Organize Folder`**: Manually queue all existing files in the target folder for background AI organization.
2. **`Change Target Folder`**: Update the directory you want to monitor and organize. 
   > [!NOTE]
   > Changing the folder automatically saves your preference, triggers a fresh scan, and seamlessly restarts the background watcher.
3. **`Scan & Index`**: Performs a database-only scan to update the local SQLite database without executing AI renames.
4. **`Restart Watcher`**: Manually restart the file system watcher service.
5. **`Quit`**: Exit the program.

---

## 🛠️ CLI Subcommands & Advanced Usage

For power users who prefer the terminal or want to run VaultSort as a background service:

### 🔍 Run via Antigravity Agent Skill
Let the Antigravity Agent handle the entire execution loop. Open your terminal in the project directory and run:
```bash
agy
```
Then instruct the agent:
> *"Run the directory organizer on my downloads"*  
> OR  
> *"Organize the D:\Downloads folder"*

### 👁️ Foreground File Watcher
Watch a directory for changes in the foreground and print log events to the console:
```bash
./organizer.exe watch
```

### 🗄️ Database Scan
Recursively scan and index file metadata into the local SQLite database without AI renaming:
```bash
./organizer.exe scan
```

### ⚙️ Windows Service Execution
Register VaultSort to run silently in the background as a Windows Service:
- **Install**: `./organizer.exe serve install`
- **Start**: `./organizer.exe serve start`
- **Stop**: `./organizer.exe serve stop`
- **Uninstall**: `./organizer.exe serve uninstall`

---

## ⚙️ Configuration & Settings

Settings are stored in `%APPDATA%/DirectoryOrganizer/settings.json` and are generated automatically on the first launch.

- `watch_dir`: The directory to monitor (defaults to `%APPDATA%/DirectoryOrganizer/watch`).
- `db_path`: The database location (defaults to `%APPDATA%/DirectoryOrganizer/organizer.db`).
- `retries`: Number of retries for calling the AI CLI.
- `retry_backoff`: Delay (seconds) between retry attempts.

---

## 🧠 Obsidian-Style Markdown Vault

Every time VaultSort organizes a file, it creates a markdown note in the `vault/` directory structure (e.g., `vault/Documents/Tax_Report_2026.md`). 

Each note logs:
- Original file path
- Modification timestamps
- Categorization context & AI reasoning
- A snippet of the file's text content (if applicable)

This unique feature turns your structured directory into a fully searchable, plain-text knowledge base!

---

## 🧬 Auto-Evolution & Self-Correction

As an Antigravity Agent Skill, VaultSort adapts to your workflow:
1. **Extractor Expansion**: If it encounters a new file format containing readable text (e.g., `.svelte`, `.yaml`) but no snippet is extracted, the agent will rewrite `cmd/extractor/main.go`, recompile, and retry.
2. **Policy Creation**: Detecting recurring file patterns prompts the agent to edit `SKILL.md`, establishing personalized categorization rules.
3. **Evolution Logging**: All autonomous changes are safely recorded in `vault/Evolution_Log_<Date>.md`.

---

## ✍️ Authors & License

- **Sparsh Bajaj**
- Licensed under the [MIT License](LICENSE).
