# Tech Stack

## Runtime
- Python 3.12+

## TUI
- Textual (rich TUI widgets, async, layout)

## CLI
- Typer (commands, options, help)

## Data
- SQLite (run history, suggestions, undo log)
- Pydantic (config and data validation)

## AI
- OpenAI-compatible client (custom base URL)
- Optional local provider support

## File Analysis
- pathlib for traversal
- python-magic or filetype for MIME detection
- pdfminer.six, python-docx, python-pptx for text extraction (optional)
- Pillow for image downsampling

## Graph
- networkx for relationship graph
- graph rendering to ASCII in TUI
- optional HTML export with pyvis (post-MVP)

## Packaging
- PyInstaller for Windows builds

## Logging
- structlog or logging with JSON output
