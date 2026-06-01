import shutil
import json
from pathlib import Path
from core.ai_renamer import SmartRenamer

class DownloadOrganizer:
    def __init__(self, config_path=None):
        import sys
        import os
        
        if config_path is None:
            # Handle PyInstaller bundled executable path
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
                config_path = os.path.join(base_path, 'config.json')
            else:
                config_path = 'config.json'
                
        self.config = self._load_config(config_path)
        self.file_lists = {category: [] for category in self.config.keys()}
        self.renamer = SmartRenamer()
        
    def _load_config(self, config_path):
        """Load and sanitize configuration file"""
        with open(config_path) as f:
            config = json.load(f)
        
        cleaned = {}
        for category, exts in config.items():
            cleaned[category] = list({
                ext.lower().strip() if ext.startswith('.') else f'.{ext.strip().lower()}'
                for ext in exts
            })
        return cleaned
    
    def organize(self, source_dir, dry_run=False, ai_rename=False):
        """Main organization routine returns list of planned moves"""
        source = Path(source_dir)
        self.file_lists = {category: [] for category in self.config.keys()}
        self._categorize_files(source)
        planned_moves = []
        summary = {"moved": 0, "skipped": 0, "errors": 0, "renamed": 0, "planned": 0}
        reserved_names = {category: set() for category in self.config.keys()}
        
        for category, files in self.file_lists.items():
            if not files:
                continue
                
            dest = source / category
            self._create_dir(dest)
            
            for file in files:
                src_path = source / file
                if not src_path.exists():
                    summary["skipped"] += 1
                    continue

                dest_name = file
                if ai_rename:
                    suggested_name = self.renamer.suggest_name(src_path)
                    dest_name = self.renamer.ensure_unique(
                        dest,
                        suggested_name,
                        reserved_names[category]
                    )
                    reserved_names[category].add(dest_name)
                    if dest_name != file:
                        summary["renamed"] += 1

                dest_path = dest / dest_name
                if dest_path.exists():
                    print(f"Skipping {file}: destination already exists.")
                    summary["skipped"] += 1
                    continue

                planned_moves.append((str(src_path), str(dest_path)))
                
                if dry_run:
                    print(f"[Dry] Would move {src_path} -> {dest_path}")
                else:
                    try:
                        shutil.move(str(src_path), str(dest_path))
                        print(f"Moved {file} to {category}")
                        summary["moved"] += 1
                    except Exception as e:
                        print(f"Error moving {file}: {str(e)}")
                        summary["errors"] += 1
        
        summary["planned"] = len(planned_moves)

        if dry_run and planned_moves:
            preview_path = source / "preview_changes.txt"
            with open(preview_path, 'w') as f:
                f.write("Planned file moves:\n\n")
                f.write("\n".join([f"{src} -> {dest}" for src, dest in planned_moves]))
            print(f"\nPreview file created: {preview_path}")
            summary["preview_path"] = str(preview_path)

        return summary
    
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