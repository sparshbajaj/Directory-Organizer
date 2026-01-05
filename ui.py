import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from core.organizer import DownloadOrganizer

class OrganizerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Download Organizer 3.0")
        
        self.organizer = DownloadOrganizer()
        # Default to user's Downloads directory for better UX
        downloads_path = Path.home() / "Downloads"
        self.source_dir = tk.StringVar(value=str(downloads_path))
        self.config_path = tk.StringVar(value="config.json")
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
        ttk.Button(self.master, text="Preview", command=lambda: self.run_organizer(dry_run=True)).grid(row=3, column=0, pady=10)
        ttk.Button(self.master, text="Organize!", command=lambda: self.run_organizer(dry_run=False)).grid(row=3, column=1, pady=10)
        ttk.Button(self.master, text="Exit", command=self.master.quit).grid(row=3, column=2, pady=10)
        
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
                
            self.organizer = DownloadOrganizer(self.config_path.get())
            self.organizer.organize(source, dry_run=dry_run)
            
            msg = "Preview complete" if dry_run else "Organization complete!"
            messagebox.showinfo("Success", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = OrganizerGUI(root)
    root.mainloop()