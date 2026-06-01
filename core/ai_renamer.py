from collections import Counter
from datetime import datetime
import json
import re
from pathlib import Path

DEFAULT_MAX_WORDS = 6
DEFAULT_MAX_LENGTH = 80
MAX_TEXT_CHARS = 20000

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rtf",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".log",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".heic", ".tiff", ".bmp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac"}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}

GENERIC_PATTERNS = [
    re.compile(r"^(img|dsc|vid|pxl|mvimg|scan)[ _-]?\d+", re.IGNORECASE),
    re.compile(r"^screenshot( \d+)?", re.IGNORECASE),
    re.compile(r"^untitled( \d+)?", re.IGNORECASE),
    re.compile(r"^document( \d+)?", re.IGNORECASE),
]

GENERIC_NAMES = {
    "file",
    "image",
    "photo",
    "video",
    "scan",
    "screenshot",
    "document",
    "untitled",
}


class SmartRenamer:
    def __init__(self, max_words=DEFAULT_MAX_WORDS, max_length=DEFAULT_MAX_LENGTH):
        self.max_words = max_words
        self.max_length = max_length

    def suggest_name(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        stem = self._normalize_stem(file_path.stem)

        contextual = self._contextual_title(file_path, ext)
        if contextual:
            stem = contextual
        elif self._is_generic_stem(stem):
            stem = self._default_title(file_path, ext)

        stem = self._sanitize(stem)
        if not stem:
            stem = "File"

        return f"{stem}{ext}"

    def ensure_unique(self, dest_dir: Path, filename: str, reserved=None) -> str:
        if reserved is None:
            reserved = set()

        candidate = filename
        stem = Path(filename).stem
        ext = Path(filename).suffix
        counter = 1

        while candidate in reserved or (dest_dir / candidate).exists():
            candidate = f"{stem} ({counter}){ext}"
            counter += 1

        return candidate

    def _contextual_title(self, file_path: Path, ext: str) -> str:
        if ext not in TEXT_EXTENSIONS:
            return ""

        text = self._read_text(file_path)
        if not text:
            return ""

        if ext == ".json":
            title = self._title_from_json(text)
            if title:
                return title

        return self._title_from_text(text)

    def _read_text(self, file_path: Path) -> str:
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                return handle.read(MAX_TEXT_CHARS)
        except OSError:
            return ""

    def _title_from_json(self, text: str) -> str:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ""

        if isinstance(data, dict):
            for key in ("title", "name", "subject", "description"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return self._shorten(value)

        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                for key in ("title", "name", "subject", "description"):
                    value = first.get(key)
                    if isinstance(value, str) and value.strip():
                        return self._shorten(value)

        return ""

    def _title_from_text(self, text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return self._shorten(cleaned)

        return self._keyword_title(text)

    def _keyword_title(self, text: str) -> str:
        words = re.findall(r"[A-Za-z][A-Za-z0-9']+", text.lower())
        words = [word for word in words if word not in STOPWORDS and len(word) > 2]
        if not words:
            return ""

        counts = Counter(words)
        top = [word for word, _ in counts.most_common(self.max_words)]
        return " ".join(word.title() for word in top)

    def _shorten(self, text: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", text)
        if not words:
            return ""
        return " ".join(words[: self.max_words]).title()

    def _default_title(self, file_path: Path, ext: str) -> str:
        try:
            timestamp = file_path.stat().st_mtime
        except OSError:
            timestamp = datetime.now().timestamp()

        date_stamp = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

        if ext in IMAGE_EXTENSIONS:
            label = "Photo"
        elif ext in VIDEO_EXTENSIONS:
            label = "Video"
        elif ext in AUDIO_EXTENSIONS:
            label = "Audio"
        elif ext in TEXT_EXTENSIONS:
            label = "Document"
        else:
            label = "File"

        return f"{label} {date_stamp}"

    def _normalize_stem(self, stem: str) -> str:
        stem = re.sub(r"[_\-.]+", " ", stem)
        stem = re.sub(r"\s+", " ", stem).strip()
        return stem

    def _sanitize(self, name: str) -> str:
        name = re.sub(r"[<>:\"/\\|?*\n\r\t]", " ", name)
        name = re.sub(r"\s+", " ", name).strip(" .")
        if len(name) > self.max_length:
            name = name[: self.max_length].rstrip()
        return name

    def _is_generic_stem(self, stem: str) -> bool:
        if not stem:
            return True

        lowered = stem.lower()
        if lowered in GENERIC_NAMES or len(lowered) < 3:
            return True

        return any(pattern.match(lowered) for pattern in GENERIC_PATTERNS)
