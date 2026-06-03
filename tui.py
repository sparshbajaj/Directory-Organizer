import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Textual imports
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Select,
    Static,
    Tree,
)
from textual.worker import get_current_worker

# Core logic imports
from core.database import DatabaseManager
from core.organizer import DownloadOrganizer, OrganizerOptions, FilePlan
from core.ai_client import AIProviderConfig, PROVIDER_PRESETS

SETTINGS_PATH = Path.home() / ".directory_organizer" / "settings.json"


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


class BrowseWidget(Horizontal):
    """A horizontal row containing a label, input, and a browse button."""
    def __init__(self, label_text: str, input_id: str, default_val: str = "", is_file: bool = False):
        super().__init__()
        self.label_text = label_text
        self.input_id = input_id
        self.default_val = default_val
        self.is_file = is_file

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, classes="field_label")
        yield Input(value=self.default_val, id=self.input_id, classes="field_input")
        yield Button("Browse", id=f"btn_browse_{self.input_id}", classes="btn_browse")


class EditNameScreen(ModalScreen[Optional[str]]):
    """Modal screen for editing a file's proposed name."""
    def __init__(self, current_name: str):
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal_dialog"):
            yield Label("Edit Proposed Name:", classes="modal_title")
            yield Input(value=self.current_name, id="edit_input")
            with Horizontal(classes="modal_buttons"):
                yield Button("Save", variant="success", id="btn_save")
                yield Button("Cancel", variant="error", id="btn_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save":
            new_name = self.query_one("#edit_input", Input).value.strip()
            self.dismiss(new_name if new_name else None)
        else:
            self.dismiss(None)


class FirstTimeSetupScreen(Screen):
    """Wizard for first time AI configuration."""
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="wizard_container"):
            yield Label("Welcome to Directory Organizer! ✨", classes="wizard_title")
            yield Label("Let's configure your AI native settings for intelligent renaming & classification.", classes="wizard_subtitle")
            
            with Vertical(classes="wizard_form"):
                yield Label("AI Provider:")
                yield Select(
                    [("Local Preset (No AI)", "local"), 
                     ("OpenAI (gpt-4o-mini)", "openai"), 
                     ("OpenRouter", "openrouter"), 
                     ("Gemini CLI", "gemini-cli"),
                     ("Claude Code CLI", "claude-cli"),
                     ("Custom API Provider", "custom")],
                    value="openai",
                    id="setup_provider"
                )
                
                yield Label("API Key:")
                yield Input(placeholder="sk-...", id="setup_key", password=True)
                
                yield Label("Base URL:")
                yield Input(value="https://api.openai.com/v1", id="setup_base_url")
                
                yield Label("Model:")
                yield Input(value="gpt-4o-mini", id="setup_model")
                
                yield Label("Vision Model (Optional):")
                yield Input(value="gpt-4o-mini", id="setup_vision_model")
                
                yield Checkbox("Consent to send content snippets for AI analysis", value=True, id="setup_consent")
                
            with Horizontal(classes="wizard_buttons"):
                yield Button("Save & Enable AI Native Mode", variant="success", id="btn_save_setup")
                yield Button("Skip / Use Local Fallback", id="btn_skip_setup")
        yield Footer()

    def on_mount(self) -> None:
        self.update_provider_fields("openai")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "setup_provider":
            self.update_provider_fields(str(event.value))

    def update_provider_fields(self, provider: str) -> None:
        base_url_input = self.query_one("#setup_base_url", Input)
        model_input = self.query_one("#setup_model", Input)
        vision_input = self.query_one("#setup_vision_model", Input)
        
        preset = PROVIDER_PRESETS.get(provider, {})
        
        if provider == "local":
            base_url_input.value = ""
            model_input.value = ""
            vision_input.value = ""
            base_url_input.disabled = True
            model_input.disabled = True
            vision_input.disabled = True
        elif provider in ["openai", "openrouter"]:
            base_url_input.value = preset.get("base_url", "")
            model_input.value = preset.get("model", "")
            vision_input.value = preset.get("model", "")
            base_url_input.disabled = True
            model_input.disabled = False
            vision_input.disabled = False
        elif provider in ["gemini-cli", "claude-cli"]:
            base_url_input.value = "CLI"
            model_input.value = "CLI"
            vision_input.value = "CLI"
            base_url_input.disabled = True
            model_input.disabled = True
            vision_input.disabled = True
        else: # custom
            base_url_input.value = "http://localhost:11434/v1"
            model_input.value = "llama3"
            vision_input.value = ""
            base_url_input.disabled = False
            model_input.disabled = False
            vision_input.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save_setup":
            provider = self.query_one("#setup_provider", Select).value
            api_key = self.query_one("#setup_key", Input).value.strip()
            base_url = self.query_one("#setup_base_url", Input).value.strip()
            model = self.query_one("#setup_model", Input).value.strip()
            vision_model = self.query_one("#setup_vision_model", Input).value.strip()
            consent = self.query_one("#setup_consent", Checkbox).value
            
            # Save settings
            settings = load_settings()
            settings.update({
                "ai_provider": provider,
                "ai_api_key": api_key,
                "ai_base_url": base_url,
                "ai_model": model,
                "ai_vision_model": vision_model,
                "ai_consent": consent,
                "ai_send_content": consent,
                "ai_rename": True if provider != "local" else False,
                "ai_classify": True if (provider != "local" and api_key) else False,
                "ai_save_key": True if api_key else False,
                "setup_completed": True,
            })
            save_settings(settings)
            self.dismiss(True)
        else:
            settings = load_settings()
            settings.update({
                "ai_provider": "local",
                "ai_rename": False,
                "ai_classify": False,
                "setup_completed": True,
            })
            save_settings(settings)
            self.dismiss(False)


class ConfigScreen(Screen):
    """The landing screen for setting options and scanning."""
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="form_container"):
            yield Label("DIRECTORY ORGANIZER", classes="app_title")
            yield Label("Terminal-first AI-assisted organizer", classes="app_subtitle")

            yield BrowseWidget("Source Directory:", "source_dir", str(Path.home() / "Downloads"))
            yield BrowseWidget("Rules Config File:", "config_path", "config.json", is_file=True)

            with Grid(classes="options_grid"):
                with Vertical():
                    yield Label("AI Integration", classes="section_header")
                    yield Checkbox("Enable AI Rename", value=True, id="ai_rename")
                    yield Checkbox("Enable AI Classification", value=True, id="ai_classify")
                    yield Checkbox("Consent to send snippet", value=True, id="ai_consent")
                    yield Checkbox("Dry Run Mode", value=True, id="dry_run")
                with Vertical():
                    yield Label("AI Credentials", classes="section_header")
                    yield Label("AI Provider:")
                    yield Select(
                        [("Local Preset", "local"), ("OpenAI", "openai"), ("OpenRouter", "openrouter"), ("Gemini CLI", "gemini-cli"), ("Claude Code CLI", "claude-cli"), ("Custom API", "custom")],
                        value="local",
                        id="ai_provider",
                    )
                    yield Label("API Key:")
                    yield Input(placeholder="API Key...", id="ai_key", password=True)
                with Vertical():
                    yield Label("AI Models & Endpoints", classes="section_header")
                    yield Label("Base URL:")
                    yield Input(id="ai_base_url")
                    yield Label("Model:")
                    yield Input(id="ai_model")
                    yield Label("Vision Model:")
                    yield Input(id="ai_vision_model")
                with Vertical():
                    yield Label("Run Logic", classes="section_header")
                    yield Label("Conflict Handling:")
                    yield Select(
                        [("Skip", "skip"), ("Overwrite", "overwrite"), ("Keep Both", "append"), ("Move to Conflict Dir", "conflicts")],
                        value="skip",
                        id="conflict_strategy",
                    )
                    yield Label("Grouping Pattern:")
                    yield Select(
                        [("None", "none"), ("By Month", "date"), ("By Project Tag", "project"), ("By Source App", "source-app")],
                        value="none",
                        id="grouping",
                    )
                    yield Label("Test Scan Limit (0=No Limit):")
                    yield Input(value="0", placeholder="Limit scanned files...", id="scan_limit")

            with Horizontal(classes="action_row"):
                yield Button("Start Scan", variant="primary", id="btn_start")
                yield Button("View Run History", id="btn_history")
                yield Button("Quit", variant="error", id="btn_quit")
        yield Footer()

    def on_mount(self) -> None:
        self.load_and_populate_settings()
        
        # Check if first-time setup is needed
        settings = load_settings()
        if not settings or not settings.get("setup_completed"):
            def handle_setup_done(result) -> None:
                self.load_and_populate_settings()
            self.app.push_screen(FirstTimeSetupScreen(), handle_setup_done)

    def load_and_populate_settings(self) -> None:
        settings = load_settings()
        
        self.query_one("#source_dir", Input).value = settings.get("source_dir", str(Path.home() / "Downloads"))
        self.query_one("#config_path", Input).value = settings.get("config_path", "config.json")
        self.query_one("#ai_provider", Select).value = settings.get("ai_provider", "local")
        self.query_one("#ai_key", Input).value = settings.get("ai_api_key", "")
        self.query_one("#ai_base_url", Input).value = settings.get("ai_base_url", "")
        self.query_one("#ai_model", Input).value = settings.get("ai_model", "")
        self.query_one("#ai_vision_model", Input).value = settings.get("ai_vision_model", "")
        
        self.query_one("#ai_rename", Checkbox).value = settings.get("ai_rename", True)
        self.query_one("#ai_classify", Checkbox).value = settings.get("ai_classify", settings.get("ai_api_key") is not None and len(settings.get("ai_api_key", "")) > 0)
        self.query_one("#ai_consent", Checkbox).value = settings.get("ai_consent", True)
        self.query_one("#dry_run", Checkbox).value = settings.get("dry_run", True)
        self.query_one("#conflict_strategy", Select).value = settings.get("conflict_strategy", "skip")
        self.query_one("#grouping", Select).value = settings.get("grouping", "none")
        self.query_one("#scan_limit", Input).value = str(settings.get("scan_limit", 0))

        # Disable/Enable appropriate fields
        self.update_provider_fields(settings.get("ai_provider", "local"))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "ai_provider":
            self.update_provider_fields(str(event.value))

    def update_provider_fields(self, provider: str) -> None:
        base_url_input = self.query_one("#ai_base_url", Input)
        model_input = self.query_one("#ai_model", Input)
        vision_input = self.query_one("#ai_vision_model", Input)
        
        preset = PROVIDER_PRESETS.get(provider, {})
        
        if provider == "local":
            base_url_input.disabled = True
            model_input.disabled = True
            vision_input.disabled = True
        elif provider in ["openai", "openrouter"]:
            base_url_input.disabled = True
            model_input.disabled = False
            vision_input.disabled = False
        elif provider in ["gemini-cli", "claude-cli"]:
            base_url_input.disabled = True
            model_input.disabled = True
            vision_input.disabled = True
        else: # custom
            base_url_input.disabled = False
            model_input.disabled = False
            vision_input.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_quit":
            self.app.exit()
        elif event.button.id == "btn_start":
            self.app.start_scan()
        elif event.button.id == "btn_history":
            self.app.push_screen(HistoryScreen())
        elif event.button.id.startswith("btn_browse_"):
            input_id = event.button.id.replace("btn_browse_", "")
            self.browse_for_path(input_id)

    def browse_for_path(self, input_id: str) -> None:
        def thread_func():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                
                is_file = input_id == "config_path"
                if is_file:
                    path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
                else:
                    path = filedialog.askdirectory()
                
                root.destroy()
                if path:
                    self.app.call_from_thread(self.update_path_value, input_id, path)
            except Exception:
                pass

        threading.Thread(target=thread_func, daemon=True).start()

    def update_path_value(self, input_id: str, path: str) -> None:
        self.query_one(f"#{input_id}", Input).value = path


class ProgressScreen(Screen):
    """Screen displayed while analysis/scanning is in progress."""
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="progress_container"):
            yield Label("Scanning folder and building AI plan...", id="progress_label")
            yield ProgressBar(id="progress_bar")
            yield Static("Analyzing files...", id="current_file_label")
        yield Footer()

    def update_progress(self, current: int, total: int, text: str) -> None:
        self.query_one("#progress_bar", ProgressBar).update(total=total, progress=current)
        self.query_one("#progress_label", Label).update(f"Analyzing files... ({current} / {total})")
        self.query_one("#current_file_label", Static).update(text)


class SuggestionsScreen(Screen):
    """Grid suggestion list screen with details view and action shortcuts."""
    BINDINGS = [
        Binding("space", "toggle_select", "Toggle Item Approval", show=True),
        Binding("e", "edit_name", "Edit Proposed Name", show=True),
        Binding("y", "apply_changes", "Apply Selection", show=True),
        Binding("m", "view_map", "Show Relationship Map", show=True),
        Binding("q", "back_to_config", "Back to Main", show=True),
    ]

    def __init__(self, plan: List[FilePlan], summary: Dict):
        super().__init__()
        self.plan = plan
        self.summary = summary
        self.current_idx = 0
        self.filter_mode = "all"  # all, rename, move, no_change

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="suggestions_layout"):
            with Vertical(classes="list_pane"):
                with Horizontal(classes="filter_buttons"):
                    yield Button("All Files", variant="primary", id="filter_all")
                    yield Button("Renames", id="filter_rename")
                    yield Button("Moves", id="filter_move")
                    yield Button("No Change", id="filter_no_change")
                yield DataTable(id="suggestions_table")
            with Vertical(classes="detail_pane"):
                yield Label("Suggestion Detail", classes="section_title")
                yield Static("", id="detail_view", classes="detail_box")
                with Vertical(classes="summary_box"):
                    yield Label("Plan Summary:", classes="summary_title")
                    yield Static("", id="summary_stats")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#suggestions_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Apply", "Original Filename", "Proposed Filename", "Category", "Size (KB)")
        self.populate_table()
        self.update_summary_stats()

    def get_filtered_plan(self) -> List[tuple]:
        filtered = []
        for idx, item in enumerate(self.plan):
            is_rename = item.original_name != item.new_name
            is_move = item.source.parent != item.dest.parent
            if self.filter_mode == "all":
                filtered.append((idx, item))
            elif self.filter_mode == "rename" and is_rename:
                filtered.append((idx, item))
            elif self.filter_mode == "move" and is_move:
                filtered.append((idx, item))
            elif self.filter_mode == "no_change" and not is_rename and not is_move:
                filtered.append((idx, item))
        return filtered

    def populate_table(self) -> None:
        table = self.query_one("#suggestions_table", DataTable)
        table.clear()
        
        filtered = self.get_filtered_plan()
        for plan_idx, item in filtered:
            status = "[x] Approved" if item.apply else "[ ] Skipped"
            table.add_row(
                status,
                item.original_name,
                item.new_name,
                item.category,
                f"{item.size // 1024}",
                key=str(plan_idx)
            )
        
        if filtered:
            table.focus()
            self.select_suggestion(0)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        plan_idx = int(event.row_key.value)
        self.select_suggestion(plan_idx)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is not None:
            plan_idx = int(event.row_key.value)
            self.select_suggestion(plan_idx)

    def select_suggestion(self, idx: int) -> None:
        self.current_idx = idx
        item = self.plan[idx]
        is_rename = item.original_name != item.new_name
        is_move = item.source.parent != item.dest.parent
        
        action = "No Change"
        if is_rename and is_move:
            action = "Rename and Move"
        elif is_rename:
            action = "Rename Only"
        elif is_move:
            action = "Move Only"

        details = (
            f"[bold cyan]Original Name:[/]\n{item.original_name}\n\n"
            f"[bold cyan]Proposed Name:[/]\n{item.new_name}\n\n"
            f"[bold cyan]Source Path:[/]\n{item.source}\n\n"
            f"[bold cyan]Destination Path:[/]\n{item.dest}\n\n"
            f"[bold cyan]Action Category:[/]\n{action} ({item.category})\n\n"
            f"[bold cyan]AI Suggestions Rationale:[/]\n{item.reason or 'Local rules criteria match.'}\n\n"
            f"[bold cyan]Status Check:[/]\n"
            f"  • Apply this plan? {'Yes' if item.apply else 'No'}\n"
            f"  • File exists at destination? {'Yes' if item.dest.exists() else 'No'}\n"
            f"  • Overwrite on match? {'Yes' if item.overwrite else 'No'}"
        )
        self.query_one("#detail_view", Static).update(details)

    def action_toggle_select(self) -> None:
        item = self.plan[self.current_idx]
        item.apply = not item.apply
        
        table = self.query_one("#suggestions_table", DataTable)
        status = "[x] Approved" if item.apply else "[ ] Skipped"
        table.update_cell(str(self.current_idx), "Apply", status)
        self.select_suggestion(self.current_idx)
        self.update_summary_stats()

    def action_edit_name(self) -> None:
        item = self.plan[self.current_idx]
        
        def handle_dismiss(new_name: Optional[str]) -> None:
            if new_name:
                item.new_name = new_name
                item.dest = item.dest.parent / new_name
                
                table = self.query_one("#suggestions_table", DataTable)
                table.update_cell(str(self.current_idx), "Proposed Filename", new_name)
                self.select_suggestion(self.current_idx)

        self.app.push_screen(EditNameScreen(item.new_name), handle_dismiss)

    def action_apply_changes(self) -> None:
        self.app.execute_plan(self.plan, self.summary)

    def action_view_map(self) -> None:
        self.app.push_screen(MapViewScreen(self.plan))

    def action_back_to_config(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id.startswith("filter_"):
            for btn_id in ["filter_all", "filter_rename", "filter_move", "filter_no_change"]:
                btn = self.query_one(f"#{btn_id}", Button)
                if btn_id == event.button.id:
                    btn.variant = "primary"
                else:
                    btn.variant = "default"
            
            self.filter_mode = event.button.id.replace("filter_", "")
            self.populate_table()

    def update_summary_stats(self) -> None:
        total_files = len(self.plan)
        approved_files = sum(1 for item in self.plan if item.apply)
        skipped_files = total_files - approved_files
        total_size = sum(item.size for item in self.plan if item.apply)

        stats = (
            f"Total Files Planned: {total_files}\n"
            f"Approved: [green]{approved_files}[/] | Skipped: [yellow]{skipped_files}[/]\n"
            f"Estimated Transfer Size: [cyan]{total_size // 1024} KB[/]"
        )
        self.query_one("#summary_stats", Static).update(stats)


class MapViewScreen(Screen):
    """Interactive Tree-based cluster view showing relations/categories."""
    BINDINGS = [
        Binding("q", "back_to_list", "Back to List", show=True),
        Binding("escape", "back_to_list", "Back to List", show=True),
    ]

    def __init__(self, plan: List[FilePlan]):
        super().__init__()
        self.plan = plan

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="map_container"):
            yield Label("Folder Structure & AI Cluster Map", classes="map_title")
            yield Tree("Root: Downloads", id="map_tree")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#map_tree", Tree)
        tree.root.expand()

        by_category = {}
        for item in self.plan:
            by_category.setdefault(item.category, []).append(item)

        for category, items in by_category.items():
            cat_node = tree.root.add(f"[bold green]📂 Category: {category}[/]", expand=True)
            for item in items:
                changed_indicator = ""
                if item.original_name != item.new_name:
                    changed_indicator = f" [bold yellow](Rename -> {item.new_name})[/]"
                cat_node.add(f"📄 {item.original_name}{changed_indicator}")

        tree.focus()

    def action_back_to_list(self) -> None:
        self.app.pop_screen()


class HistoryScreen(Screen):
    """View database run logs and run undo rollbacks."""
    BINDINGS = [
        Binding("u", "undo_selected", "Undo Selected Run", show=True),
        Binding("q", "back_to_main", "Back to Main", show=True),
        Binding("escape", "back_to_main", "Back to Main", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="history_layout"):
            with Vertical(classes="history_list_pane"):
                yield Label("Database Run History", classes="section_title")
                yield DataTable(id="history_table")
            with Vertical(classes="history_detail_pane"):
                yield Label("Run Details", classes="section_title")
                yield Static("Select a run to inspect.", id="history_detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#history_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Run ID", "Timestamp", "Moved", "Skipped")
        self.populate_table()

    def populate_table(self) -> None:
        table = self.query_one("#history_table", DataTable)
        table.clear()
        
        runs = self.app.db.get_run_history()
        for r in runs:
            table.add_row(
                r["id"][:8],
                r["started_at"].replace("T", " ")[:19],
                str(r["changes_applied"]),
                str(r["changes_skipped"]),
                key=r["id"]
            )
        
        if runs:
            table.focus()
            self.select_run(runs[0]["id"])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.select_run(event.row_key.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is not None:
            self.select_run(event.row_key.value)

    def select_run(self, run_id: str) -> None:
        self.selected_run_id = run_id
        runs = self.app.db.get_run_history()
        run = next((r for r in runs if r["id"] == run_id), None)
        if not run:
            return

        suggestions = self.app.db.get_suggestions(run_id)
        applied = [s for s in suggestions if s["apply"] == 1]
        
        detail_lines = [
            f"[bold cyan]Run UUID:[/]\n{run['id']}\n",
            f"[bold cyan]Started At:[/]\n{run['started_at'].replace('T', ' ')[:19]}\n",
            f"[bold cyan]Finished At:[/]\n{(run['finished_at'] or 'Aborted').replace('T', ' ')[:19]}\n",
            f"[bold cyan]Files Organized:[/]\n{run['changes_applied']} approved, {run['changes_skipped']} skipped\n",
            f"\n[bold green]Files Affected ({len(applied)}):[/]"
        ]
        
        for s in applied[:15]:
            detail_lines.append(f"  • {s['original_name']} -> {s['proposed_name']}")
        if len(applied) > 15:
            detail_lines.append(f"  ... and {len(applied) - 15} more files.")

        self.query_one("#history_detail", Static).update("\n".join(detail_lines))

    def action_undo_selected(self) -> None:
        undo_log = self.app.db.get_undo_log(self.selected_run_id)
        if not undo_log:
            self.app.show_message_modal("Cannot Undo", "This run has already been undone or has no undo operations.")
            return

        result = self.app.organizer.undo_last_run()
        msg = f"Undo successful! Restored {result.get('restored', 0)} files."
        if result.get("errors"):
            msg += f"\nErrors: {result.get('errors')}"
        
        self.app.show_message_modal("Rollback Complete", msg)
        self.populate_table()

    def action_back_to_main(self) -> None:
        self.app.pop_screen()


class MessageModal(ModalScreen):
    """Simple popup message dialog."""
    def __init__(self, title: str, message: str):
        super().__init__()
        self.title_text = title
        self.message_text = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal_dialog"):
            yield Label(self.title_text, classes="modal_title")
            yield Static(self.message_text, classes="modal_message")
            yield Button("OK", variant="primary", id="btn_ok")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class OrganizerApp(App):
    """The central application manager for the Directory Organizer."""
    
    CSS = """
    Screen {
        background: #1e1e1e;
        color: #e0e0e0;
    }

    Header {
        background: #111111;
        color: #00ffff;
        text-style: bold;
    }

    Footer {
        background: #111111;
        color: #888888;
    }

    .form_container {
        padding: 1 2;
        align: center middle;
    }

    .app_title {
        text-style: bold;
        color: #00ffff;
        margin-bottom: 0;
    }

    .app_subtitle {
        color: #888888;
        margin-bottom: 1;
    }

    .field_label {
        width: 20;
        content-align: right middle;
        margin-right: 2;
    }

    .field_input {
        width: 50;
        margin-bottom: 1;
    }

    .btn_browse {
        margin-left: 2;
        height: 3;
    }

    .options_grid {
        grid-size: 4;
        grid-gutter: 2;
        height: 18;
        margin-top: 1;
        margin-bottom: 1;
    }

    .section_header {
        text-style: bold;
        color: #00ff00;
        border-bottom: solid #00ff00;
        margin-bottom: 1;
    }

    .action_row {
        align: center middle;
        margin-top: 1;
        height: 4;
    }

    .action_row Button {
        margin-right: 2;
    }

    /* Suggestions Layout */
    .suggestions_layout {
        height: 100%;
    }

    .list_pane {
        width: 60%;
        border-right: tall #333333;
        padding: 1;
    }

    .filter_buttons {
        height: 3;
        margin-bottom: 1;
    }

    .filter_buttons Button {
        margin-right: 1;
    }

    .detail_pane {
        width: 40%;
        padding: 1;
    }

    .section_title {
        text-style: bold;
        color: #00ffff;
        margin-bottom: 1;
    }

    .detail_box {
        height: 65%;
        border: solid #00ffff;
        background: #252525;
        padding: 1;
        overflow-y: scroll;
        margin-bottom: 1;
    }

    .summary_box {
        height: 25%;
        border: solid #888888;
        padding: 1;
    }

    .summary_title {
        text-style: bold;
        color: #ffaa00;
    }

    /* Modal dialog */
    .modal_dialog {
        background: #252525;
        border: double #00ffff;
        width: 50;
        height: auto;
        padding: 2;
        align: center middle;
    }

    .modal_title {
        text-style: bold;
        color: #00ffff;
        margin-bottom: 1;
    }

    .modal_message {
        margin-bottom: 2;
    }

    .modal_buttons {
        align: right middle;
    }

    .modal_buttons Button {
        margin-left: 2;
    }

    /* Map view container */
    .map_container {
        padding: 2;
    }

    .map_title {
        text-style: bold;
        color: #00ff00;
        margin-bottom: 2;
    }

    #map_tree {
        border: tall #00ff00;
        height: 80%;
        background: #1a1a1a;
    }

    /* History Layout */
    .history_layout {
        height: 100%;
    }

    .history_list_pane {
        width: 50%;
        border-right: tall #333333;
        padding: 1;
    }

    .history_detail_pane {
        width: 50%;
        padding: 1;
    }

    .history_detail_pane Static {
        height: 80%;
        border: solid #00ffff;
        padding: 1;
        background: #252525;
        overflow-y: scroll;
    }

    /* Progress Screen */
    .progress_container {
        align: center middle;
        padding: 4;
    }

    #progress_bar {
        width: 60;
        margin-top: 1;
        margin-bottom: 1;
    }

    /* Wizard Style */
    .wizard_container {
        padding: 2 4;
        align: center middle;
    }

    .wizard_title {
        text-style: bold;
        color: #00ffff;
        margin-bottom: 1;
    }

    .wizard_subtitle {
        color: #888888;
        margin-bottom: 2;
    }

    .wizard_form {
        border: solid #00ffff;
        background: #252525;
        padding: 1 3;
        width: 65;
        height: 22;
        overflow-y: scroll;
        margin-bottom: 2;
    }

    .wizard_form Label {
        margin-top: 1;
        color: #00ff00;
        text-style: bold;
    }

    .wizard_form Input {
        margin-bottom: 1;
        width: 55;
    }

    .wizard_buttons {
        align: center middle;
        height: 4;
    }

    .wizard_buttons Button {
        margin-right: 2;
    }
    """

    def __init__(self):
        super().__init__()
        self.organizer = DownloadOrganizer()
        self.db = DatabaseManager()

    def on_mount(self) -> None:
        self.push_screen(ConfigScreen())

    def show_message_modal(self, title: str, message: str) -> None:
        self.push_screen(MessageModal(title, message))

    def start_scan(self) -> None:
        config_screen = self.screen
        source_dir = config_screen.query_one("#source_dir", Input).value.strip()
        config_path = config_screen.query_one("#config_path", Input).value.strip()
        
        # AI Config
        ai_rename = config_screen.query_one("#ai_rename", Checkbox).value
        ai_classify = config_screen.query_one("#ai_classify", Checkbox).value
        ai_consent = config_screen.query_one("#ai_consent", Checkbox).value
        ai_provider = config_screen.query_one("#ai_provider", Select).value
        ai_key = config_screen.query_one("#ai_key", Input).value.strip()
        ai_base_url = config_screen.query_one("#ai_base_url", Input).value.strip()
        ai_model = config_screen.query_one("#ai_model", Input).value.strip()
        ai_vision_model = config_screen.query_one("#ai_vision_model", Input).value.strip()

        # Logic Config
        dry_run = config_screen.query_one("#dry_run", Checkbox).value
        conflict_strategy = config_screen.query_one("#conflict_strategy", Select).value
        grouping = config_screen.query_one("#grouping", Select).value

        # Test Scan Limit
        scan_limit_str = config_screen.query_one("#scan_limit", Input).value.strip()
        try:
            scan_limit = int(scan_limit_str) if scan_limit_str else 0
            if scan_limit < 0:
                scan_limit = 0
        except ValueError:
            scan_limit = 0

        # Build options
        ai_config = AIProviderConfig(
            provider=ai_provider,
            base_url=ai_base_url,
            model=ai_model,
            vision_model=ai_vision_model,
            api_key=ai_key,
            consent=ai_consent,
            send_content=ai_consent,
        )
        options = OrganizerOptions(
            ai_rename=ai_rename,
            ai_classify=ai_classify,
            ai_config=ai_config,
            conflict_strategy=conflict_strategy,
            grouping=grouping,
            scan_limit=scan_limit,
        )

        # Save settings on scan
        settings = {
            "source_dir": source_dir,
            "config_path": config_path,
            "ai_provider": ai_provider,
            "ai_api_key": ai_key,
            "ai_base_url": ai_base_url,
            "ai_model": ai_model,
            "ai_vision_model": ai_vision_model,
            "ai_consent": ai_consent,
            "ai_send_content": ai_consent,
            "ai_rename": ai_rename,
            "ai_classify": ai_classify,
            "dry_run": dry_run,
            "conflict_strategy": conflict_strategy,
            "grouping": grouping,
            "scan_limit": scan_limit,
        }
        save_settings(settings)

        progress_screen = ProgressScreen()
        self.push_screen(progress_screen)

        # Worker for background file scanning and planning
        def run_planning():
            worker = get_current_worker()
            
            def report_progress(current: int, total: int, text: str):
                if not worker.is_cancelled:
                    self.call_from_thread(progress_screen.update_progress, current, total, text)

            try:
                org = DownloadOrganizer(config_path if config_path else None)
                plan, summary = org.build_plan(Path(source_dir), options, progress_callback=report_progress)
                self.call_from_thread(self.on_planning_done, plan, summary, options, source_dir, dry_run)
            except Exception as e:
                self.call_from_thread(self.on_planning_failed, str(e))

        self.run_worker(run_planning, thread=True)

    def on_planning_done(self, plan: List[FilePlan], summary: Dict, options: OrganizerOptions, source_dir: str, dry_run: bool) -> None:
        self.pop_screen()  # Remove ProgressScreen
        self.push_screen(SuggestionsScreen(plan, summary))
        self.current_options = options
        self.current_source_dir = source_dir
        self.current_dry_run = dry_run

    def on_planning_failed(self, error_msg: str) -> None:
        self.pop_screen()
        self.show_message_modal("Scanning Failed", f"An error occurred during scan:\n{error_msg}")

    def execute_plan(self, plan: List[FilePlan], summary: Dict) -> None:
        progress_screen = ProgressScreen()
        self.push_screen(progress_screen)

        def run_execution():
            worker = get_current_worker()
            
            def report_progress(current: int, total: int, text: str):
                if not worker.is_cancelled:
                    self.call_from_thread(progress_screen.update_progress, current, total, text)

            try:
                org = DownloadOrganizer()
                result = org.organize(
                    Path(self.current_source_dir),
                    dry_run=self.current_dry_run,
                    options=self.current_options,
                    plan=plan,
                    summary=summary,
                    progress_callback=report_progress
                )
                self.call_from_thread(self.on_execution_done, result)
            except Exception as e:
                self.call_from_thread(self.on_execution_failed, str(e))

        self.run_worker(run_execution, thread=True)

    def on_execution_done(self, result: Dict) -> None:
        self.pop_screen()  # ProgressScreen
        self.pop_screen()  # SuggestionsScreen (return to main)
        
        details = (
            f"Scan Complete!\n\n"
            f"📂 Files Moved: {result.get('moved', 0)}\n"
            f"⚠️ Files Skipped: {result.get('skipped', 0)}\n"
            f"❌ Errors Encountered: {result.get('errors', 0)}\n\n"
            f"Operation logged to Database history."
        )
        self.show_message_modal("Success", details)

    def on_execution_failed(self, error_msg: str) -> None:
        self.pop_screen()
        self.show_message_modal("Execution Failed", f"Failed to apply plan:\n{error_msg}")


if __name__ == "__main__":
    OrganizerApp().run()
