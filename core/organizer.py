import json
import shutil
import mimetypes
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.ai_renamer import SmartRenamer, sanitize_filename
from core.ai_client import AIClient, AIProviderConfig, AINameCache


DEFAULT_CONFLICT_STRATEGY = "skip"
DEFAULT_GROUPING = "none"


@dataclass
class OrganizerOptions:
    ai_rename: bool = False
    ai_classify: bool = False
    ai_config: AIProviderConfig = field(default_factory=AIProviderConfig)
    conflict_strategy: str = DEFAULT_CONFLICT_STRATEGY
    min_size_bytes: int = 0
    min_age_minutes: int = 0
    ignored_folders: List[str] = field(default_factory=list)
    grouping: str = DEFAULT_GROUPING
    tag_folders: bool = False
    allow_unknown: bool = True
    ai_batch_size: int = 1
    ai_batch_pause_ms: int = 0


@dataclass
class FilePlan:
    source: Path
    dest: Path
    category: str
    original_name: str
    new_name: str
    apply: bool = True
    overwrite: bool = False
    size: int = 0
    reason: str = ""


class DownloadOrganizer:
    def __init__(self, config_path: Optional[str] = None):
        import sys
        import os

        if config_path is None:
            if getattr(sys, "frozen", False):
                base_path = os.path.dirname(sys.executable)
                config_path = os.path.join(base_path, "config.json")
            else:
                config_path = "config.json"

        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.renamer = SmartRenamer()
        self.cache_path = Path.home() / ".directory_organizer" / "ai_cache.json"
        self.undo_path = Path.home() / ".directory_organizer" / "undo_log.json"

    def _load_config(self, config_path: str) -> Dict[str, List[str]]:
        with open(config_path) as f:
            config = json.load(f)

        cleaned = {}
        for category, exts in config.items():
            cleaned[category] = list(
                {
                    ext.lower().strip() if ext.startswith(".") else f".{ext.strip().lower()}"
                    for ext in exts
                }
            )
        return cleaned

    def build_plan(
        self, 
        source_dir: Path, 
        options: Optional[OrganizerOptions] = None,
        progress_callback: Optional[callable] = None
    ) -> Tuple[List[FilePlan], Dict]:
        options = options or OrganizerOptions()
        source = Path(source_dir)
        summary = {
            "planned": 0,
            "skipped": 0,
            "errors": 0,
            "renamed": 0,
            "details": [],
            "category_counts": {},
            "total_size": 0,
            "bytes_saved": 0,
            "data_sent": [],
        }
        plan: List[FilePlan] = []
        reserved_names: Dict[Path, set] = {}

        ai_client = AIClient(options.ai_config, AINameCache(self.cache_path)) if (options.ai_rename or options.ai_classify) else None

        items = []
        for item in source.rglob("*"):
            if item.is_dir():
                continue
            if not item.is_file():
                continue
            if self._is_ignored(item, source, options.ignored_folders):
                continue
            items.append(item)

        total = len(items)
        ai_counter = 0

        for idx, item in enumerate(items):
            if progress_callback:
                progress_callback(idx + 1, total, f"Analyzing {item.name}...")

            size = item.stat().st_size
            if options.min_size_bytes and size < options.min_size_bytes:
                summary["skipped"] += 1
                summary["details"].append(self._detail(item, "skipped", "below min size"))
                continue

            age_minutes = (time.time() - item.stat().st_mtime) / 60
            if options.min_age_minutes and age_minutes < options.min_age_minutes:
                summary["skipped"] += 1
                summary["details"].append(self._detail(item, "skipped", "too new"))
                continue

            category = self._determine_category(item)
            if not category and options.ai_classify and ai_client:
                category, data_sent = ai_client.suggest_category(item, list(self.config.keys()))
                if data_sent:
                    summary["data_sent"].append(data_sent)

            if not category and options.allow_unknown:
                category = "Other"
                if "Other" not in self.config:
                    self.config["Other"] = []
            if not category:
                summary["skipped"] += 1
                summary["details"].append(self._detail(item, "skipped", "unknown type"))
                continue

            tag = self._group_tag(item, options.grouping)
            if item.parent != source:
                dest_dir = item.parent
            else:
                dest_dir = source / category
                if tag:
                    if options.tag_folders:
                        dest_dir = dest_dir / tag
                    else:
                        dest_dir = source / f"{category} - {tag}"

            reserved = reserved_names.setdefault(dest_dir, set())
            dest_name = item.name
            rename_reason = ""
            if options.ai_rename:
                ai_counter += 1
                if progress_callback:
                    progress_callback(
                        idx + 1,
                        total,
                        f"AI rename {ai_counter}/{total}: {item.name}",
                    )
                dest_name, data_sent, used_ai, ai_error = self._suggest_ai_name(item, ai_client, options.ai_config)
                if data_sent:
                    summary["data_sent"].append(data_sent)

                if used_ai:
                    if dest_name and dest_name != item.name:
                        summary["renamed"] += 1
                        rename_reason = "ai-rename"
                    else:
                        rename_reason = "ai-nochange"
                else:
                    if dest_name and dest_name != item.name:
                        summary["renamed"] += 1
                        rename_reason = "local-rename"
                    else:
                        rename_reason = "local-nochange"

                if ai_error:
                    rename_reason = f"ai-error:{ai_error}"
                    summary["details"].append(self._detail(item, "warning", f"AI rename failed: {ai_error}"))

                if options.ai_rename and not dest_name:
                    summary["details"].append(self._detail(item, "warning", "AI rename failed, using original"))

                dest_name = dest_name or item.name
                if options.ai_batch_pause_ms and options.ai_batch_size > 0:
                    if ai_counter % options.ai_batch_size == 0:
                        time.sleep(options.ai_batch_pause_ms / 1000)

            ext = item.suffix
            stem = sanitize_filename(Path(dest_name).stem)
            if stem:
                dest_name = f"{stem}{ext}"
            else:
                dest_name = item.name

            dest_path = dest_dir / dest_name
            if dest_path.resolve() == item.resolve():
                summary["skipped"] += 1
                summary["details"].append(self._detail(item, "skipped", "already in place"))
                continue
            overwrite = False
            if dest_path.exists() or dest_name in reserved:
                dest_path, dest_name, overwrite, reason = self._resolve_conflict(
                    dest_dir, dest_name, options.conflict_strategy, reserved, source
                )
                if dest_path is None:
                    summary["skipped"] += 1
                    summary["bytes_saved"] += size
                    summary["details"].append(self._detail(item, "skipped", reason))
                    continue
            reserved.add(dest_name)

            summary["planned"] += 1
            summary["total_size"] += size
            summary["category_counts"][category] = summary["category_counts"].get(category, 0) + 1
            plan.append(
                FilePlan(
                    source=item,
                    dest=dest_path,
                    category=category,
                    original_name=item.name,
                    new_name=dest_name,
                    overwrite=overwrite,
                    size=size,
                    reason=rename_reason,
                )
            )

        summary["top_categories"] = sorted(
            summary["category_counts"].items(), key=lambda item: item[1], reverse=True
        )[:3]
        summary["recent_activity"] = self._recent_activity()
        return plan, summary

    def _is_ignored(self, path: Path, source: Path, ignored: List[str]) -> bool:
        if not ignored:
            return False
        try:
            parts = path.relative_to(source).parts
        except ValueError:
            return False
        return any(part in ignored for part in parts)

    def organize(
        self,
        source_dir: Path,
        dry_run: bool = False,
        ai_rename: bool = False,
        options: Optional[OrganizerOptions] = None,
        plan: Optional[List[FilePlan]] = None,
        summary: Optional[Dict] = None,
        progress_callback: Optional[callable] = None,
    ) -> Dict:
        options = options or OrganizerOptions(ai_rename=ai_rename)
        if plan is None:
            plan, summary = self.build_plan(source_dir, options, progress_callback=progress_callback)
        else:
            summary = summary or {
                "planned": len(plan),
                "details": [],
                "errors": 0,
                "moved": 0,
                "skipped": 0,
                "renamed": 0,
                "category_counts": {},
                "total_size": 0,
                "bytes_saved": 0,
                "top_categories": [],
            }

        return self._execute_plan(source_dir, plan, summary, dry_run, progress_callback=progress_callback)

    def _execute_plan(
        self, 
        source_dir: Path, 
        plan: List[FilePlan], 
        summary: Dict, 
        dry_run: bool,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        undo_ops = []
        total = len(plan)
        for idx, item in enumerate(plan):
            if progress_callback:
                progress_callback(idx + 1, total, f"Processing {item.source.name}...")

            if not item.apply:
                summary["skipped"] += 1
                summary["details"].append(self._detail(item.source, "skipped", "not approved"))
                continue

            if not item.source.exists():
                summary["skipped"] += 1
                summary["details"].append(self._detail(item.source, "skipped", "missing"))
                continue

            item.dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if item.dest.exists() and item.overwrite and not dry_run:
                    item.dest.unlink()

                if dry_run:
                    summary["details"].append(self._detail(item.source, "planned", "dry run"))
                    continue

                shutil.move(str(item.source), str(item.dest))
                undo_ops.append({"from": str(item.dest), "to": str(item.source), "size": item.size})
                summary["moved"] = summary.get("moved", 0) + 1
                summary["details"].append(self._detail(item.source, "moved", ""))
            except Exception as e:
                summary["errors"] = summary.get("errors", 0) + 1
                summary["details"].append(self._detail(item.source, "error", str(e)))

        if dry_run and plan:
            preview_path = Path(source_dir) / "preview_changes.txt"
            try:
                with preview_path.open("w", encoding="utf-8", errors="replace") as handle:
                    handle.write("Planned file moves:\n\n")
                    for item in plan:
                        if item.apply:
                            handle.write(f"{item.source} -> {item.dest}\n")
                summary["preview_path"] = str(preview_path)
            except OSError:
                pass

        if not dry_run:
            self._write_undo_log(source_dir, undo_ops)

        return summary

    def undo_last_run(self) -> Dict:
        if not self.undo_path.exists():
            return {"errors": 0, "restored": 0, "details": [], "message": "No undo history found."}
        try:
            data = json.loads(self.undo_path.read_text())
        except json.JSONDecodeError:
            return {"errors": 0, "restored": 0, "details": [], "message": "Undo history is corrupted."}

        if not data:
            return {"errors": 0, "restored": 0, "details": [], "message": "No undo history found."}

        last = data.pop()
        restored = 0
        errors = 0
        details = []
        for op in last.get("operations", []):
            src = Path(op["from"])
            dest = Path(op["to"])
            if not src.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            unique_name = self.renamer.ensure_unique(dest.parent, dest.name)
            dest_path = dest.parent / unique_name
            try:
                shutil.move(str(src), str(dest_path))
                restored += 1
            except Exception as e:
                errors += 1
                details.append({"file": str(src), "status": "error", "message": str(e)})

        try:
            self.undo_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

        return {"errors": errors, "restored": restored, "details": details}

    def _write_undo_log(self, source_dir: Path, operations: List[Dict]) -> None:
        if not operations:
            return
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": str(source_dir),
            "operations": operations,
        }
        history = []
        if self.undo_path.exists():
            try:
                history = json.loads(self.undo_path.read_text())
            except json.JSONDecodeError:
                history = []
        history.append(entry)
        self.undo_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.undo_path.write_text(json.dumps(history, indent=2))
        except OSError:
            pass

    def _detail(self, file_path: Path, status: str, message: str) -> Dict:
        return {"file": str(file_path), "status": status, "message": message}

    def _determine_category(self, file_path: Path) -> Optional[str]:
        ext = file_path.suffix.lower()
        for category, exts in self.config.items():
            if ext in exts:
                return category

        signature = self._category_from_signature(file_path)
        if signature:
            return signature

        mime, _ = mimetypes.guess_type(file_path.name)
        if mime:
            if mime.startswith("image/"):
                return "Pictures"
            if mime.startswith("video/"):
                return "Videos"
            if mime.startswith("audio/"):
                return "Music"
            if mime in {"application/pdf"}:
                return "Books"
        return None

    def _category_from_signature(self, file_path: Path) -> Optional[str]:
        try:
            with file_path.open("rb") as handle:
                header = handle.read(16)
        except OSError:
            return None

        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "Pictures"
        if header.startswith(b"\xff\xd8\xff"):
            return "Pictures"
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return "Pictures"
        if header.startswith(b"%PDF"):
            return "Books"
        if header.startswith(b"PK\x03\x04"):
            return "Compressed"
        if header.startswith(b"ID3") or header.startswith(b"RIFF"):
            return "Music"
        if len(header) >= 12 and header[4:8] == b"ftyp":
            return "Videos"
        return None

    def _group_tag(self, file_path: Path, grouping: str) -> str:
        grouping = (grouping or "none").lower()
        if grouping == "date":
            try:
                timestamp = file_path.stat().st_mtime
            except OSError:
                timestamp = time.time()
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m")
        if grouping == "project":
            stem = file_path.stem.replace("_", " ").replace("-", " ")
            token = stem.split()[0] if stem.split() else ""
            return token.title() if len(token) >= 3 else ""
        if grouping == "source-app":
            lower = file_path.name.lower()
            for key, label in {
                "whatsapp": "WhatsApp",
                "slack": "Slack",
                "discord": "Discord",
                "zoom": "Zoom",
                "teams": "Teams",
                "chrome": "Chrome",
                "firefox": "Firefox",
                "edge": "Edge",
            }.items():
                if key in lower:
                    return label
        return ""

    def _resolve_conflict(
        self,
        dest_dir: Path,
        dest_name: str,
        strategy: str,
        reserved: set,
        source: Path,
    ) -> Tuple[Optional[Path], str, bool, str]:
        strategy = (strategy or DEFAULT_CONFLICT_STRATEGY).lower()
        dest_path = dest_dir / dest_name
        if strategy == "skip":
            return None, dest_name, False, "conflict"
        if strategy == "overwrite":
            return dest_path, dest_name, True, ""
        if strategy in {"append", "append counter", "keep both", "keep_both"}:
            unique = self.renamer.ensure_unique(dest_dir, dest_name, reserved)
            return dest_dir / unique, unique, False, ""
        if strategy == "conflicts":
            conflict_dir = source / "Conflicts"
            conflict_dir.mkdir(exist_ok=True)
            unique = self.renamer.ensure_unique(conflict_dir, dest_name, reserved)
            return conflict_dir / unique, unique, False, ""
        unique = self.renamer.ensure_unique(dest_dir, dest_name, reserved)
        return dest_dir / unique, unique, False, ""

    def _suggest_ai_name(
        self,
        file_path: Path,
        ai_client: Optional[AIClient],
        ai_config: AIProviderConfig,
    ) -> Tuple[str, Dict, bool, str]:
        if not ai_client:
            return self.renamer.suggest_name(file_path), {}, False, ""

        suggestion, data_sent, ai_error = ai_client.suggest_name(file_path)
        if not suggestion:
            suggestion = self.renamer.suggest_name(file_path)
            return suggestion, data_sent, False, ai_error

        ext = file_path.suffix.lower()
        stem = sanitize_filename(suggestion)
        if stem.lower().endswith(ext):
            stem = sanitize_filename(Path(stem).stem)
        if not stem:
            return self.renamer.suggest_name(file_path), data_sent, False, ai_error
        return f"{stem}{ext}", data_sent, True, ""

    def _recent_activity(self) -> List[Dict]:
        if not self.undo_path.exists():
            return []
        try:
            data = json.loads(self.undo_path.read_text())
        except json.JSONDecodeError:
            return []
        return data[-5:]
