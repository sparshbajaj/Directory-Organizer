# Product Requirements Document (PRD)

## Overview
A terminal-first, AI-assisted download organizer that scans a folder, analyzes file content and metadata, builds a visual map of related files, and suggests safe renames and folder placement. Users review suggestions in a TUI and apply changes with strong guardrails and undo.

## Goals
- Make downloads easy to find later with consistent, meaningful names and structure.
- Provide clear, reviewable AI suggestions with opt-out and undo.
- Visualize relationships between files (projects, topics, versions) in a terminal map view.
- Operate safely on large folders with predictable performance.

## Non-Goals
- Full web UI in v1 (can export to HTML graph later).
- Automatic bulk changes without user review.
- Cloud sync or multi-user features.

## Users
- Power users with messy Downloads folders.
- Professionals handling many documents, installers, and media.

## User Stories
- As a user, I can scan a folder and see a graph-like map of related files.
- As a user, I can review AI rename and move suggestions and approve them.
- As a user, I can see why a rename was suggested.
- As a user, I can undo the last run.

## Functional Requirements
- Scan and index all files in a target folder recursively.
- Build a relationship graph using:
  - filename similarity, timestamps, size, and extension
  - AI content/topic analysis (default enabled)
  - optional user tags
- Show a TUI with:
  - scan configuration
  - progress and per-file status
  - list of suggested changes with filters
  - detail pane with AI rationale
  - map view (graph + clusters)
- Suggest rename and folder placement or leave unchanged when appropriate.
- Apply changes with atomic, ordered operations and rollback on failure.
- Store run history and allow undo of the last run.

## AI Requirements
- Default enabled with a clear consent notice.
- Only send content for supported text/image types.
- Do not send binary payloads (zip, docx, exe) as content.
- Enforce output validation (no prompt-like or garbage outputs).
- Provide rationale tags (topic, project, type).

## Non-Functional Requirements
- Must handle 10k+ files without crashing.
- All actions must be reversible (undo last run).
- Clear logging and dry-run preview file.
- Configurable timeouts and batching.

## Success Metrics
- % of suggestions approved by user.
- Reduction in duplicate or vague filenames.
- Time to locate a file after organization.
- Zero data-loss incidents.

## Assumptions
- User runs locally on Windows with Python.
- Users can provide an AI key if required.

## Open Questions
- Preferred AI provider defaults?
- Max file size for text extraction?

## Milestones
- M1: TUI shell + scan + preview list.
- M2: AI analysis + rename validation.
- M3: Graph map view + export.
- M4: Undo + history.
