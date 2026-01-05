import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from core.organizer import DownloadOrganizer
import json

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, organizer):
        super().__init__(parent)
        self.title("Settings")
        self.organizer = organizer
        self.config = self.organizer.get_config().copy() # Work on a copy

        self.create_widgets()

    def create_widgets(self):
        # Layout: Left side listbox of categories, Right side details (Name, Extensions)

        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Left Panel: Categories ---
        left_panel = ttk.LabelFrame(self.main_frame, text="Categories", padding="5")
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.category_listbox = tk.Listbox(left_panel, height=15)
        self.category_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.category_listbox.bind('<<ListboxSelect>>', self.on_category_select)

        scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=self.category_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.category_listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="+", width=3, command=self.add_category).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="-", width=3, command=self.remove_category).pack(side=tk.LEFT)

        # --- Right Panel: Details ---
        right_panel = ttk.LabelFrame(self.main_frame, text="Details", padding="5")
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_panel, text="Extensions (comma separated):").pack(anchor=tk.W)
        self.extensions_var = tk.StringVar()
        self.extensions_entry = ttk.Entry(right_panel, textvariable=self.extensions_var)
        self.extensions_entry.pack(fill=tk.X, pady=(0, 10))
        self.extensions_entry.bind('<FocusOut>', self.save_current_selection)

        ttk.Label(right_panel, text="Example: .jpg, .png, .gif").pack(anchor=tk.W, style="Small.TLabel")

        # --- Bottom: Buttons ---
        bottom_frame = ttk.Frame(self, padding="10")
        bottom_frame.pack(fill=tk.X)

        ttk.Button(bottom_frame, text="Save & Close", command=self.save_and_close).pack(side=tk.RIGHT)
        ttk.Button(bottom_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.refresh_list()

    def refresh_list(self):
        self.category_listbox.delete(0, tk.END)
        for category in sorted(self.config.keys()):
            self.category_listbox.insert(tk.END, category)

    def on_category_select(self, event):
        selection = self.category_listbox.curselection()
        if selection:
            category = self.category_listbox.get(selection[0])
            extensions = self.config.get(category, [])
            self.extensions_var.set(", ".join(sorted(extensions)))
            self.current_category = category
        else:
            self.current_category = None
            self.extensions_var.set("")

    def save_current_selection(self, event=None):
        if hasattr(self, 'current_category') and self.current_category:
            ext_str = self.extensions_var.get()
            # Parse extensions
            exts = [e.strip() for e in ext_str.split(',') if e.strip()]
            # Ensure they start with .
            clean_exts = []
            for e in exts:
                if not e.startswith('.'):
                    clean_exts.append('.' + e)
                else:
                    clean_exts.append(e)
            self.config[self.current_category] = clean_exts

    def add_category(self):
        new_cat = simpledialog.askstring("New Category", "Enter category name:")
        if new_cat:
            if new_cat in self.config:
                messagebox.showerror("Error", "Category already exists!")
            else:
                self.config[new_cat] = []
                self.refresh_list()
                # Select the new item
                idx = self.category_listbox.get(0, tk.END).index(new_cat)
                self.category_listbox.selection_clear(0, tk.END)
                self.category_listbox.selection_set(idx)
                self.category_listbox.event_generate("<<ListboxSelect>>")

    def remove_category(self):
        selection = self.category_listbox.curselection()
        if selection:
            category = self.category_listbox.get(selection[0])
            if messagebox.askyesno("Confirm", f"Delete category '{category}'?"):
                del self.config[category]
                self.refresh_list()
                self.extensions_var.set("")
                self.current_category = None

    def save_and_close(self):
        # Save any pending edit in the entry box
        self.save_current_selection()

        # Update organizer config
        self.organizer.config = self.config

        # Save to file
        # We try to use the path from organizer, or default to config.json
        save_path = self.organizer.config_path
        if not save_path:
             save_path = "config.json"

        if self.organizer.save_config(save_path):
             messagebox.showinfo("Saved", f"Configuration saved to {save_path}")
             self.destroy()
        else:
             messagebox.showerror("Error", "Failed to save configuration file.")


class OrganizerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Download Organizer 3.0")
        
        self.organizer = DownloadOrganizer()
        self.source_dir = tk.StringVar()
        self.config_path = tk.StringVar(value=self.organizer.config_path)
        self.dry_run = tk.BooleanVar(value=False)
        
        self.create_widgets()
        
    def create_widgets(self):
        # Source Directory Selection
        ttk.Label(self.master, text="Source Directory:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(self.master, textvariable=self.source_dir, width=40).grid(row=0, column=1, padx=5)
        ttk.Button(self.master, text="Browse...", command=self.select_source_dir).grid(row=0, column=2, padx=5)
        
        # Config File Selection
        ttk.Label(self.master, text="Config File:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Entry(self.master, textvariable=self.config_path, width=40).grid(row=1, column=1, padx=5)
        ttk.Button(self.master, text="Browse...", command=self.select_config).grid(row=1, column=2, padx=5)
        
        # Options
        ttk.Checkbutton(self.master, text="Dry Run (Preview Only)", variable=self.dry_run).grid(row=2, column=1, sticky=tk.W)
        
        # Action Buttons
        btn_frame = ttk.Frame(self.master)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)

        ttk.Button(btn_frame, text="Preview", command=lambda: self.run_organizer(dry_run=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Organize!", command=lambda: self.run_organizer(dry_run=False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Settings", command=self.open_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Exit", command=self.master.quit).pack(side=tk.LEFT, padx=5)
        
    def select_source_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(directory)
            
    def select_config(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            self.config_path.set(filepath)
            # Reload organizer with new config
            self.organizer = DownloadOrganizer(filepath)
            
    def open_settings(self):
        # Ensure organizer uses the path in the text box if it changed
        current_config_path = self.config_path.get()
        if current_config_path != self.organizer.config_path:
             self.organizer = DownloadOrganizer(current_config_path)

        SettingsDialog(self.master, self.organizer)

    def run_organizer(self, dry_run=False):
        try:
            source = Path(self.source_dir.get())
            if not source.exists():
                raise ValueError("Selected directory does not exist")

            # Refresh config path in case user changed entry manually
            current_config_path = self.config_path.get()
            if current_config_path != self.organizer.config_path:
                 self.organizer = DownloadOrganizer(current_config_path)
                
            self.organizer.organize(source, dry_run=dry_run)
            
            msg = "Preview complete" if dry_run else "Organization complete!"
            messagebox.showinfo("Success", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = OrganizerGUI(root)
    root.mainloop()
