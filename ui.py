import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from core.organizer import DownloadOrganizer

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
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text="Directory Organizer", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        ttk.Label(container, text="Source folder").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=self.source_dir, width=42).grid(
            row=1, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(container, text="Browse", command=self.select_source_dir).grid(row=1, column=2)

        ttk.Label(container, text="Config file").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=self.config_path, width=42).grid(
            row=2, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(container, text="Browse", command=self.select_config).grid(row=2, column=2)

        options = ttk.Frame(container)
        options.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 6))
        ttk.Checkbutton(options, text="Preview only", variable=self.dry_run).grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Checkbutton(options, text="AI rename", variable=self.ai_rename).grid(row=0, column=1, sticky="w")

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Preview", command=lambda: self.run_organizer(dry_run=True)).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Organize", command=lambda: self.run_organizer(dry_run=False)).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Exit", command=self.master.quit).grid(row=0, column=2)
        
    def select_source_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(directory)
            
    def select_config(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            self.config_path.set(filepath)
            
    def run_organizer(self, dry_run=False):
        try:
            source = Path(self.source_dir.get())
            if not source.exists():
                raise ValueError("Selected directory does not exist")

            dry_run = dry_run or self.dry_run.get()
            self.organizer = DownloadOrganizer(self.config_path.get())
            summary = self.organizer.organize(source, dry_run=dry_run, ai_rename=self.ai_rename.get())

            if dry_run:
                title = "Preview complete"
                count = summary.get("planned", 0)
                details = f"Planned {count} moves."
                preview_path = summary.get("preview_path")
                if preview_path:
                    details = f"{details}\nPreview saved to {preview_path}"
            else:
                title = "Organization complete!"
                details = f"Moved {summary.get('moved', 0)} files."

            if summary.get("renamed"):
                details = f"{details}\nRenamed {summary['renamed']} files."
            if summary.get("skipped"):
                details = f"{details}\nSkipped {summary['skipped']} files."
            if summary.get("errors"):
                details = f"{details}\nErrors: {summary['errors']}."

            messagebox.showinfo("Success", f"{title}\n{details}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = OrganizerGUI(root)
    root.mainloop()