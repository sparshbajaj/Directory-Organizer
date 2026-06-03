# Data Model

## FileItem
- id: uuid
- path: string
- name: string
- ext: string
- size_bytes: int
- created_at: datetime
- modified_at: datetime
- mime: string
- hash: string (optional)

## Suggestion
- id: uuid
- file_id: uuid
- action: rename | move | no_change
- proposed_name: string
- proposed_path: string
- confidence: float
- rationale: string
- ai_tags: list[string]
- risk: low | medium | high

## Link
- id: uuid
- source_file_id: uuid
- target_file_id: uuid
- reason: string (name_similarity | content_topic | time_cluster)
- weight: float

## RunConfig
- id: uuid
- root_path: string
- dry_run: bool
- ai_enabled: bool
- ai_provider: string
- batch_size: int
- batch_pause_ms: int

## RunHistory
- id: uuid
- started_at: datetime
- finished_at: datetime
- summary: string
- changes_applied: int
- changes_skipped: int

## UndoLog
- id: uuid
- run_id: uuid
- operations: json
