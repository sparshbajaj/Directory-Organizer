---
name: directory-organizer
description: Automatically scans a target folder recursively, extracts file context using Go, protects projects/apps, suggests intelligent filenames/categories, auto-evolves its own code, and maintains an Obsidian-style markdown vault.
---

# Directory Organizer Skill (Auto-Evolving, Recursive)

This skill organizes files in a target directory (defaulting to the user's Downloads folder). It leverages a fast Go utility to extract file metadata and content snippets. Furthermore, **this skill is self-modifying**—it can evolve its own logic based on the files it encounters.

## Execution Steps

When a user triggers this skill, follow these exact steps:

### 1. Identify Target & Extract Context
1. Default to `D:\Downloads` unless the user specifies otherwise.
2. Run the Go extractor utility:
   ```bash
   go run cmd/extractor/main.go "D:\Downloads"
   ```
   *Note: This script recursively scans sub-folders, but uses "Project Boundary Detection" to keep application bundles and git repositories intact!*
3. Read the outputted JSON data. Pay special attention to the `is_project_folder` boolean and the full `absolute_path` of items.

### 2. Auto-Evolution Phase (Meta-Prompting)
Analyze the JSON data for missing capabilities and **modify your own codebase** using your file-editing tools (`replace_file_content`):
*   **Evolve Extractor (`main.go`)**: If you see files that are clearly text-based or code (e.g., `.svelte`, `.terraform`, `.conf`, `.env`) but their `content_snippet` is empty because the extension is missing from the `textExts` map in `cmd/extractor/main.go`, **use your tool to edit `cmd/extractor/main.go`**. Add the extension to the map, save it, and re-run step 1 before proceeding!
*   **Evolve Categories (`SKILL.md`)**: If you notice a repeated pattern of specific file types (e.g., lots of `.stl` or `.obj` files, or `.fig` design files), **edit this very `SKILL.md` file**. Add a new standard category (e.g., `3D Models` or `Design Assets`) to the "Suggest Enhancements" section below so you remember it for all future runs.
*   **Log Evolution**: If you made any evolutionary changes, create a file named `vault/Evolution_Log_<Date>.md` detailing exactly what you taught yourself.

### 3. Analyze and Plan
For each item in the JSON:
- **If `is_project_folder: true`**: Do NOT suggest moving the contents of this directory. Treat the whole folder as a single unit. Suggest moving/renaming the top-level folder itself to the correct Category (e.g., `Projects`, `Apps`, `Code`). Keep the folder contents intact.
- **If `is_project_folder: false` (normal file)**: Assign it to a logical Category folder (e.g., `Documents`, `Images`, `Media`). Suggest a cleaner, descriptive name based on the content. *If it was nested in a useless sub-folder, your action will effectively move it out of that sub-folder and into the Category!*

### 4. Present and Execute
1. Show the user a markdown table of your planned changes: `Original Item` | `Proposed Name` | `Target Category`. (Clarify if an item is a Project Folder or a File).
2. Once the user approves the plan, execute standard shell commands (e.g., PowerShell `Move-Item`) to move and rename the files/folders.

### 5. Update the Markdown Vault
For *every* file/folder successfully organized, create an Obsidian-style markdown note in `vault/<Category>/<New_Name>.md`:
```markdown
# <New_Name>

**Original Path:** <absolute_path>
**Date Organized:** <Current_Date>
**Category:** <Target Category>
**Is Project/App Bundle:** <true/false>

## Extracted Context
<Insert the content_snippet from the JSON here if it exists>
```

## Suggest Enhancements
- **Category: Design Assets** (for `.xd`, `.fig`, `.aep`, `.psd` files)
