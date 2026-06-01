import json
import threading
import time
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from core.organizer import DownloadOrganizer, OrganizerOptions, FilePlan
from core.ai_client import AIProviderConfig, AIClient, AINameCache


SETTINGS_PATH = Path.home() / ".directory_organizer" / "settings.json"


class OrganizerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Directory Organizer")
        master.configure(padx=20, pady=20)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.organizer = DownloadOrganizer()
        self.source_dir = tk.StringVar()
        self.config_path = tk.StringVar(value="config.json")
        self.dry_run = tk.BooleanVar(value=False)
        self.ai_rename = tk.BooleanVar(value=True)
        self.conflict_strategy = tk.StringVar(value="skip")
        self.min_size_kb = tk.IntVar(value=0)
        self.min_age_minutes = tk.IntVar(value=0)
        self.ignored_folders = tk.StringVar()
        self.grouping = tk.StringVar(value="none")
        self.tag_folders = tk.BooleanVar(value=True)
        self.watch_mode = tk.BooleanVar(value=False)
        self.watch_interval = tk.IntVar(value=15)
        self.watch_throttle = tk.IntVar(value=30)

        self.ai_provider = tk.StringVar(value="local")
        self.ai_base_url = tk.StringVar()
        self.ai_model = tk.StringVar()
        self.ai_api_key = tk.StringVar()
        self.ai_temperature = tk.DoubleVar(value=0.2)
        self.ai_max_tokens = tk.IntVar(value=48)
        self.ai_timeout = tk.IntVar(value=20)
        self.ai_consent = tk.BooleanVar(value=True)
        self.ai_send_content = tk.BooleanVar(value=True)
        self.ai_save_key = tk.BooleanVar(value=False)

        self.status_text = tk.StringVar(value="Ready.")
        self.preview_window = None
        self.preview_plan = []
        self.preview_defaults = []
        self.preview_summary = None
        self.last_summary = None
        self.last_source = None
        self._watch_job = None
        self._watch_snapshot = {}
        self._last_watch_run = 0.0

        self._load_settings()
        self._configure_style()
        self.create_widgets()

    def _configure_style(self):
        style = ttk.Style(self.master)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        else:
            style.theme_use("clam")

        style.configure("Title.TLabel", font=("Helvetica Neue", 16, "bold"))
        style.configure("TLabel", font=("Helvetica Neue", 11))
        style.configure("TButton", padding=(12, 6))
        style.configure("TEntry", padding=(4, 4))
        style.configure("TCheckbutton", padding=(4, 2))

    def create_widgets(self):
        container = ttk.Frame(self.master)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Directory Organizer", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )

        notebook = ttk.Notebook(container)
        notebook.grid(row=1, column=0, sticky="nsew")
        container.rowconfigure(1, weight=1)

        main_tab = ttk.Frame(notebook)
        ai_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Organize")
        notebook.add(ai_tab, text="AI Settings")

        self._build_main_tab(main_tab)
        self._build_ai_tab(ai_tab)

        status = ttk.Label(container, textvariable=self.status_text)
        status.grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _build_main_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Source folder").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.source_dir, width=42).grid(
            row=0, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(parent, text="Browse", command=self.select_source_dir).grid(row=0, column=2)

        ttk.Label(parent, text="Config file").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.config_path, width=42).grid(
            row=1, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(parent, text="Browse", command=self.select_config).grid(row=1, column=2)

        options = ttk.LabelFrame(parent, text="Options")
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        options.columnconfigure(1, weight=1)

        ttk.Checkbutton(options, text="Preview only", variable=self.dry_run).grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(options, text="Use AI for renaming", variable=self.ai_rename).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(options, text="Conflict handling").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            options,
            textvariable=self.conflict_strategy,
            values=["skip", "overwrite", "append", "keep both", "conflicts"],
            state="readonly",
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(options, text="Grouping").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            options,
            textvariable=self.grouping,
            values=["none", "date", "project", "source-app"],
            state="readonly",
        ).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Checkbutton(options, text="Tag folders", variable=self.tag_folders).grid(
            row=2, column=2, sticky="w", padx=(12, 0)
        )

        filters = ttk.LabelFrame(parent, text="Filters")
        filters.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        filters.columnconfigure(1, weight=1)

        ttk.Label(filters, text="Min size (KB)").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(filters, textvariable=self.min_size_kb, width=8).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(filters, text="Min age (minutes)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(filters, textvariable=self.min_age_minutes, width=8).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(filters, text="Ignored folders (comma-separated)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(filters, textvariable=self.ignored_folders).grid(row=2, column=1, sticky="ew", pady=4)

        watch = ttk.LabelFrame(parent, text="Watch mode")
        watch.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        watch.columnconfigure(1, weight=1)

        ttk.Checkbutton(watch, text="Enable watch mode", variable=self.watch_mode, command=self.toggle_watch).grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Label(watch, text="Interval (sec)").grid(row=0, column=1, sticky="w")
        ttk.Entry(watch, textvariable=self.watch_interval, width=6).grid(row=0, column=2, sticky="w")
        ttk.Label(watch, text="Throttle (sec)").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Entry(watch, textvariable=self.watch_throttle, width=6).grid(row=0, column=4, sticky="w")

        actions = ttk.Frame(parent)
        actions.grid(row=5, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Edit Rules", command=self.open_rule_editor).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Preview", command=self.preview_changes).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Organize", command=lambda: self.run_organizer(dry_run=False)).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(actions, text="Undo last run", command=self.undo_last_run).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Exit", command=self.master.quit).grid(row=0, column=4)

    def _build_ai_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Provider").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.ai_provider,
            values=["local", "openai", "openrouter", "custom"],
            state="readonly",
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(parent, text="Base URL").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_base_url).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Model").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_model).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="API key").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_api_key, show="*").grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(parent, text="Save API key in config", variable=self.ai_save_key).grid(
            row=3, column=2, sticky="w", padx=(12, 0)
        )

        ttk.Label(parent, text="Temperature").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_temperature, width=6).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Max tokens").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_max_tokens, width=6).grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Timeout (sec)").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.ai_timeout, width=6).grid(row=6, column=1, sticky="w", pady=4)

        ttk.Checkbutton(parent, text="Consent to send data", variable=self.ai_consent).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Checkbutton(parent, text="Send content snippet (1-2 pages)", variable=self.ai_send_content).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=4
        )

        data_notice = (
            "Data sent: file name, extension, size, and optional first 1-2 pages of text for text files."
        )
        ttk.Label(parent, text=data_notice, wraplength=420).grid(row=9, column=0, columnspan=3, sticky="w", pady=6)

        actions = ttk.Frame(parent)
        actions.grid(row=10, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(actions, text="Test connection", command=self.test_ai_connection).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Preview AI rename", command=self.preview_ai_rename).grid(row=0, column=1)

    def _load_settings(self):
        if not SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(SETTINGS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return

        self.source_dir.set(data.get("source_dir", ""))
        self.config_path.set(data.get("config_path", "config.json"))
        self.ai_provider.set(data.get("ai_provider", "local"))
        self.ai_base_url.set(data.get("ai_base_url", ""))
        self.ai_model.set(data.get("ai_model", ""))
        self.ai_temperature.set(data.get("ai_temperature", 0.2))
        self.ai_max_tokens.set(data.get("ai_max_tokens", 48))
        self.ai_timeout.set(data.get("ai_timeout", 20))
        self.ai_consent.set(data.get("ai_consent", True))
        self.ai_send_content.set(data.get("ai_send_content", True))
        self.ai_save_key.set(data.get("ai_save_key", False))
        if data.get("ai_save_key"):
            self.ai_api_key.set(data.get("ai_api_key", ""))

        self.conflict_strategy.set(data.get("conflict_strategy", "skip"))
        self.min_size_kb.set(data.get("min_size_kb", 0))
        self.min_age_minutes.set(data.get("min_age_minutes", 0))
        self.ignored_folders.set(data.get("ignored_folders", ""))
        self.grouping.set(data.get("grouping", "none"))
        self.tag_folders.set(data.get("tag_folders", True))
        self.watch_interval.set(data.get("watch_interval", 15))
        self.watch_throttle.set(data.get("watch_throttle", 30))

    def _save_settings(self):
        data = {
            "source_dir": self.source_dir.get(),
            "config_path": self.config_path.get(),
            "ai_provider": self.ai_provider.get(),
            "ai_base_url": self.ai_base_url.get(),
            "ai_model": self.ai_model.get(),
            "ai_temperature": self.ai_temperature.get(),
            "ai_max_tokens": self.ai_max_tokens.get(),
            "ai_timeout": self.ai_timeout.get(),
            "ai_consent": self.ai_consent.get(),
            "ai_send_content": self.ai_send_content.get(),
            "ai_save_key": self.ai_save_key.get(),
            "conflict_strategy": self.conflict_strategy.get(),
            "min_size_kb": self.min_size_kb.get(),
            "min_age_minutes": self.min_age_minutes.get(),
            "ignored_folders": self.ignored_folders.get(),
            "grouping": self.grouping.get(),
            "tag_folders": self.tag_folders.get(),
            "watch_interval": self.watch_interval.get(),
            "watch_throttle": self.watch_throttle.get(),
        }
        if self.ai_save_key.get():
            data["ai_api_key"] = self.ai_api_key.get()

        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            SETTINGS_PATH.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _gather_options(self) -> OrganizerOptions:
        ignored = [item.strip() for item in self.ignored_folders.get().split(",") if item.strip()]
        ai_config = AIProviderConfig(
            provider=self.ai_provider.get(),
            base_url=self.ai_base_url.get(),
            model=self.ai_model.get(),
            api_key=self.ai_api_key.get(),
            temperature=self.ai_temperature.get(),
            max_tokens=self.ai_max_tokens.get(),
            timeout=self.ai_timeout.get(),
            consent=self.ai_consent.get(),
            send_content=self.ai_send_content.get(),
        )
        return OrganizerOptions(
            ai_rename=self.ai_rename.get(),
            ai_config=ai_config,
            conflict_strategy=self.conflict_strategy.get(),
            min_size_bytes=max(self.min_size_kb.get(), 0) * 1024,
            min_age_minutes=max(self.min_age_minutes.get(), 0),
            ignored_folders=ignored,
            grouping=self.grouping.get(),
            tag_folders=self.tag_folders.get(),
            allow_unknown=True,
        )

    def select_source_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(directory)
            self._save_settings()

    def select_config(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            self.config_path.set(filepath)
            self._save_settings()

    def preview_changes(self):
        self.run_organizer(dry_run=True)

    def preview_ai_rename(self):
        self.ai_rename.set(True)
        self.run_organizer(dry_run=True)

    def run_organizer(self, dry_run=False):
        try:
            source = Path(self.source_dir.get())
            if not source.exists():
                raise ValueError("Selected directory does not exist")

            self._save_settings()
            options = self._gather_options()
            self.organizer = DownloadOrganizer(self.config_path.get())
            plan, summary = self.organizer.build_plan(source, options)
            self.last_source = source

            if dry_run or self.dry_run.get():
                summary = self.organizer.organize(source, dry_run=True, options=options, plan=plan, summary=summary)
                self.show_preview(plan, summary, options)
                return

            summary = self.organizer.organize(source, dry_run=False, options=options, plan=plan, summary=summary)
            self.last_summary = summary
            self._show_summary(summary)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_preview(self, plan, summary, options):
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()

        self.preview_plan = plan
        self.preview_defaults = [item.apply for item in plan]
        self.preview_summary = summary

        window = tk.Toplevel(self.master)
        window.title("Preview changes")
        window.geometry("820x420")
        self.preview_window = window

        tree = ttk.Treeview(window, columns=("apply", "old", "new", "category", "size"), show="headings")
        tree.heading("apply", text="Apply")
        tree.heading("old", text="Old name")
        tree.heading("new", text="New name")
        tree.heading("category", text="Category")
        tree.heading("size", text="Size KB")
        tree.column("apply", width=60, anchor="center")
        tree.column("old", width=200)
        tree.column("new", width=200)
        tree.column("category", width=120)
        tree.column("size", width=80, anchor="e")

        for idx, item in enumerate(plan):
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=("Yes" if item.apply else "No", item.original_name, item.new_name, item.category, item.size // 1024),
            )

        tree.pack(fill="both", expand=True, padx=10, pady=10)
        tree.bind("<Double-1>", lambda event: self.toggle_preview_item(tree))

        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(controls, text="Select all", command=lambda: self.set_preview_selection(tree, True)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(controls, text="Select none", command=lambda: self.set_preview_selection(tree, False)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(controls, text="Undo selection", command=lambda: self.reset_preview_selection(tree)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(controls, text="Apply selected", command=lambda: self.apply_preview(tree, options)).pack(
            side="right"
        )

        if summary.get("preview_path"):
            ttk.Label(window, text=f"Preview saved to {summary['preview_path']}").pack(anchor="w", padx=10)

    def toggle_preview_item(self, tree):
        selected = tree.focus()
        if not selected:
            return
        idx = int(selected)
        item = self.preview_plan[idx]
        item.apply = not item.apply
        tree.set(selected, "apply", "Yes" if item.apply else "No")

    def set_preview_selection(self, tree, state: bool):
        for idx, item in enumerate(self.preview_plan):
            item.apply = state
            tree.set(str(idx), "apply", "Yes" if state else "No")

    def reset_preview_selection(self, tree):
        for idx, item in enumerate(self.preview_plan):
            item.apply = self.preview_defaults[idx]
            tree.set(str(idx), "apply", "Yes" if item.apply else "No")

    def apply_preview(self, tree, options):
        if not self.last_source:
            return
        summary = self.organizer.organize(
            self.last_source,
            dry_run=False,
            options=options,
            plan=self.preview_plan,
            summary=self.preview_summary,
        )
        self.last_summary = summary
        if self.preview_window:
            self.preview_window.destroy()
        self._show_summary(summary)

    def _show_summary(self, summary):
        title = "Organization complete!"
        details = f"Moved {summary.get('moved', 0)} files."
        if summary.get("renamed"):
            details = f"{details}\nRenamed {summary['renamed']} files."
        if summary.get("skipped"):
            details = f"{details}\nSkipped {summary['skipped']} files."
        if summary.get("errors"):
            details = f"{details}\nErrors: {summary['errors']}."

        top_categories = summary.get("top_categories")
        if top_categories:
            details = f"{details}\nTop categories: {', '.join([f'{c} ({n})' for c, n in top_categories])}"

        if summary.get("bytes_saved"):
            details = f"{details}\nStorage savings: {summary['bytes_saved'] // 1024} KB"

        if summary.get("recent_activity"):
            details = f"{details}\nRecent activity entries: {len(summary['recent_activity'])}"

        messagebox.showinfo("Summary", f"{title}\n{details}")
        if summary.get("details"):
            self.show_report(summary)

    def show_report(self, summary):
        window = tk.Toplevel(self.master)
        window.title("Run report")
        window.geometry("700x360")

        tree = ttk.Treeview(window, columns=("file", "status", "message"), show="headings")
        tree.heading("file", text="File")
        tree.heading("status", text="Status")
        tree.heading("message", text="Message")
        tree.column("file", width=300)
        tree.column("status", width=80)
        tree.column("message", width=300)

        for item in summary.get("details", []):
            tree.insert("", "end", values=(item.get("file"), item.get("status"), item.get("message", "")))

        tree.pack(fill="both", expand=True, padx=10, pady=10)

        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(controls, text="Retry failed", command=self.retry_failed).pack(side="left")

    def retry_failed(self):
        if not self.last_summary or not self.last_source:
            return
        failed = {item["file"] for item in self.last_summary.get("details", []) if item.get("status") == "error"}
        if not failed:
            messagebox.showinfo("Retry", "No failed items to retry.")
            return
        options = self._gather_options()
        plan, _ = self.organizer.build_plan(self.last_source, options)
        retry_plan = [item for item in plan if str(item.source) in failed]
        summary = self.organizer.organize(self.last_source, dry_run=False, options=options, plan=retry_plan)
        self._show_summary(summary)

    def undo_last_run(self):
        result = self.organizer.undo_last_run()
        message = f"Restored {result.get('restored', 0)} files."
        if result.get("errors"):
            message = f"{message}\nErrors: {result.get('errors')}."
        if result.get("message"):
            message = result.get("message")
        messagebox.showinfo("Undo", message)

    def open_rule_editor(self):
        editor = tk.Toplevel(self.master)
        editor.title("Rule editor")
        editor.geometry("600x360")

        config_path = Path(self.config_path.get())
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}

        listbox = tk.Listbox(editor)
        listbox.pack(side="left", fill="y", padx=(10, 0), pady=10)
        for category in sorted(config.keys()):
            listbox.insert("end", category)

        detail_frame = ttk.Frame(editor)
        detail_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        ttk.Label(detail_frame, text="Category").grid(row=0, column=0, sticky="w")
        category_var = tk.StringVar()
        category_entry = ttk.Entry(detail_frame, textvariable=category_var)
        category_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(detail_frame, text="Extensions (comma-separated)").grid(row=1, column=0, sticky="w")
        extensions_var = tk.StringVar()
        extensions_entry = ttk.Entry(detail_frame, textvariable=extensions_var)
        extensions_entry.grid(row=1, column=1, sticky="ew", pady=4)

        detail_frame.columnconfigure(1, weight=1)

        def load_selected(event=None):
            selection = listbox.curselection()
            if not selection:
                return
            name = listbox.get(selection[0])
            category_var.set(name)
            extensions_var.set(", ".join(config.get(name, [])))

        listbox.bind("<<ListboxSelect>>", load_selected)

        def add_or_update():
            name = category_var.get().strip()
            if not name:
                return
            exts = [ext.strip() for ext in extensions_var.get().split(",") if ext.strip()]
            config[name] = exts
            if name not in listbox.get(0, "end"):
                listbox.insert("end", name)

        def remove_category():
            selection = listbox.curselection()
            if not selection:
                return
            name = listbox.get(selection[0])
            config.pop(name, None)
            listbox.delete(selection[0])
            category_var.set("")
            extensions_var.set("")

        def save_and_close():
            try:
                config_path.write_text(json.dumps(config, indent=2))
                self.organizer = DownloadOrganizer(self.config_path.get())
            except OSError:
                pass
            editor.destroy()

        buttons = ttk.Frame(detail_frame)
        buttons.grid(row=2, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(buttons, text="Add/Update", command=add_or_update).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Remove", command=remove_category).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Save", command=save_and_close).grid(row=0, column=2)

    def toggle_watch(self):
        if self.watch_mode.get():
            self._watch_snapshot = self._capture_snapshot()
            self._schedule_watch()
            self.status_text.set("Watch mode enabled.")
        else:
            if self._watch_job:
                self.master.after_cancel(self._watch_job)
                self._watch_job = None
            self.status_text.set("Watch mode disabled.")

    def _capture_snapshot(self):
        source = Path(self.source_dir.get())
        snapshot = {}
        if not source.exists():
            return snapshot
        for item in source.iterdir():
            if item.is_file():
                try:
                    snapshot[str(item)] = item.stat().st_mtime
                except OSError:
                    continue
        return snapshot

    def _schedule_watch(self):
        interval = max(self.watch_interval.get(), 5)
        self._watch_job = self.master.after(interval * 1000, self._poll_watch)

    def _poll_watch(self):
        if not self.watch_mode.get():
            return
        snapshot = self._capture_snapshot()
        new_files = [path for path in snapshot if path not in self._watch_snapshot]
        throttle = max(self.watch_throttle.get(), 0)
        if new_files and (time.time() - self._last_watch_run) >= throttle:
            self._last_watch_run = time.time()
            self.status_text.set(f"Watch: organizing {len(new_files)} new files.")
            source = Path(self.source_dir.get())
            options = self._gather_options()

            def _run():
                self.organizer = DownloadOrganizer(self.config_path.get())
                summary = self.organizer.organize(source, dry_run=False, options=options)
                self.last_summary = summary
                self.master.after(0, lambda: self._update_watch_status(summary))

            threading.Thread(target=_run, daemon=True).start()
        self._watch_snapshot = snapshot
        self._schedule_watch()

    def _update_watch_status(self, summary):
        moved = summary.get("moved", 0)
        errors = summary.get("errors", 0)
        self.status_text.set(f"Watch: moved {moved} files, errors {errors}.")

    def test_ai_connection(self):
        options = self._gather_options()
        ai_config = options.ai_config
        if ai_config.provider == "local":
            messagebox.showinfo("AI test", "Local provider selected.")
            return
        if not ai_config.consent:
            messagebox.showwarning("AI test", "Consent is required before testing.")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp:
            temp.write(b"Sample content for AI rename test.")
            temp_path = Path(temp.name)
        client = AIClient(ai_config, AINameCache(self.organizer.cache_path))
        suggestion, _ = client.suggest_name(temp_path)
        temp_path.unlink(missing_ok=True)
        if suggestion:
            messagebox.showinfo("AI test", f"Connection OK. Sample name: {suggestion}")
        else:
            messagebox.showwarning("AI test", "No response from provider. Check settings.")


if __name__ == "__main__":
    root = tk.Tk()
    app = OrganizerGUI(root)
    root.mainloop()
