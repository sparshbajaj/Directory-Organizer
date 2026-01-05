import os
import shutil
import json
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "Videos": [".mp4", ".mkv", ".avi", ".mpg", ".mov", ".wmv", ".flv", ".mpg"],
    "Pictures": [".gif", ".jpg", ".png", ".jpeg", ".cr2", ".nef", ".bmp", ".tiff", ".svg", ".ico", ".JPG"],
    "Music": [".aac", ".mp3", ".wma", ".wav"],
    "Compressed": [".zip", ".rar", ".tar", ".tar.gz", ".tgz", ".bz", ".7z", ".tgz", ".tar.bz2"],
    "Books": [".pdf", ".epub"],
    "Documents": [".doc", ".docx", ".txt", ".ppt", ".pptx", ".pdf", ".rtf", ".csv", ".xls", ".xlsx"],
    "Programs": [".exe", ".msi"],
    "VirtualDisk": [".vmdk", ".ova", ".iso", ".img"],
    "Extras": [".html", ".c", ".cpp", ".torrent", ".ino", "ttf", ".otf", ".ipa", "apk", ".lottie", ".json"],
    "Scripts": [".py", ".sh", ".bat", ".ps1"],
    "Adobe": [".xd", ".ai", ".psd", ".svg", ".eps"]
}

class DownloadOrganizer:
    def __init__(self, config_path=None):
        self.config_path = config_path
        if self.config_path is None:
            # Handle PyInstaller bundled executable path
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
                self.config_path = os.path.join(base_path, 'config.json')
            else:
                self.config_path = 'config.json'
                
        self.config = self._load_config(self.config_path)
        self.file_lists = {category: [] for category in self.config.keys()}
        
    def _load_config(self, config_path):
        """Load configuration from file or use defaults"""
        config = DEFAULT_CONFIG.copy()

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    file_config = json.load(f)
                    # We can either merge or replace.
                    # Usually a user config replaces the defaults completely to allow removing categories.
                    # Or we can do a deep merge.
                    # The requirement implies "default config directly in defaults setting",
                    # but "if user want they can change it".
                    # I will assume the file overrides the entire config structure to allow full customization.
                    if isinstance(file_config, dict):
                        config = file_config
            except (json.JSONDecodeError, OSError) as e:
                print(f"Error loading config file: {e}. Using defaults.")
        
        return self._sanitize_config(config)

    def _sanitize_config(self, config):
        cleaned = {}
        for category, exts in config.items():
            cleaned[category] = list({
                ext.lower().strip() if ext.startswith('.') else f'.{ext.strip().lower()}'
                for ext in exts
            })
        return cleaned

    def save_config(self, filepath=None):
        """Save current configuration to a file"""
        path = filepath if filepath else self.config_path
        try:
            with open(path, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get_config(self):
        """Return current configuration"""
        return self.config
    
    def organize(self, source_dir, dry_run=False):
        """Main organization routine returns list of planned moves"""
        source = Path(source_dir)
        self.file_lists = {category: [] for category in self.config.keys()} # Reset lists
        self._categorize_files(source)
        planned_moves = []
        
        for category, files in self.file_lists.items():
            if not files:
                continue
                
            dest = source / category
            self._create_dir(dest)
            
            for file in files:
                src_path = source / file
                dest_path = dest / file
                planned_moves.append((str(src_path), str(dest_path)))
                
                if dry_run:
                    print(f"[Dry] Would move {src_path} -> {dest_path}")
                else:
                    try:
                        shutil.move(str(src_path), str(dest_path))
                        print(f"Moved {file} to {category}")
                    except Exception as e:
                        print(f"Error moving {file}: {str(e)}")
        
        if dry_run and planned_moves:
            preview_path = source / "preview_changes.txt"
            with open(preview_path, 'w') as f:
                f.write("Planned file moves:\n\n")
                f.write("\n".join([f"{src} -> {dest}" for src, dest in planned_moves]))
            print(f"\nPreview file created: {preview_path}")
    
    def _categorize_files(self, source_dir):
        """Categorize files based on config"""
        for item in source_dir.iterdir():
            if item.is_file():
                for category, exts in self.config.items():
                    if item.suffix.lower() in exts:
                        self.file_lists[category].append(item.name)
                        break
    
    def _create_dir(self, path):
        """Create directory if needed"""
        if not path.exists():
            path.mkdir()
            print(f"Created directory: {path.name}")
