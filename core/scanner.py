from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import mimetypes


@dataclass(frozen=True)
class FileMetadata:
    path: Path
    name: str
    extension: str
    size: int
    modified_time: float
    mime_type: str
    is_binary: bool


class FileScanner:
    def __init__(self, ignore_dirs: set[str] | None = None, ignore_extensions: set[str] | None = None):
        self.ignore_dirs = {name.strip() for name in (ignore_dirs or set()) if name.strip()}
        self.ignore_extensions = {
            (ext if ext.startswith(".") else f".{ext}").lower().strip()
            for ext in (ignore_extensions or set())
            if ext.strip()
        }

    def scan(self, root: str | Path) -> list[FileMetadata]:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            return []

        results: list[FileMetadata] = []
        for current_root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

            current_path = Path(current_root)
            for filename in files:
                file_path = current_path / filename
                extension = file_path.suffix.lower()
                if extension in self.ignore_extensions:
                    continue

                try:
                    stat = file_path.stat()
                except OSError:
                    continue

                mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                results.append(
                    FileMetadata(
                        path=file_path,
                        name=file_path.name,
                        extension=extension,
                        size=stat.st_size,
                        modified_time=stat.st_mtime,
                        mime_type=mime_type,
                        is_binary=self._is_binary(file_path),
                    )
                )

        return results

    @staticmethod
    def _is_binary(path: Path, sample_size: int = 1024) -> bool:
        try:
            with path.open("rb") as file:
                chunk = file.read(sample_size)
        except OSError:
            return True

        if not chunk:
            return False

        if b"\x00" in chunk:
            return True

        text_bytes = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x7F)))
        non_text = chunk.translate(None, text_bytes)
        return (len(non_text) / len(chunk)) > 0.30
