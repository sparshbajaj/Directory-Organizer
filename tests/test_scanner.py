import tempfile
import unittest
from pathlib import Path

from core.scanner import FileScanner


class FileScannerTests(unittest.TestCase):
    def test_scans_files_with_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_file = root / "notes.txt"
            text_file.write_text("hello world", encoding="utf-8")

            scanner = FileScanner()
            files = scanner.scan(root)

            self.assertEqual(len(files), 1)
            metadata = files[0]
            self.assertEqual(metadata.name, "notes.txt")
            self.assertEqual(metadata.extension, ".txt")
            self.assertEqual(metadata.size, len("hello world"))
            self.assertFalse(metadata.is_binary)

    def test_ignores_configured_directories_and_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            (root / "skip.log").write_text("skip", encoding="utf-8")

            ignored_dir = root / "node_modules"
            ignored_dir.mkdir()
            (ignored_dir / "inside.txt").write_text("ignored", encoding="utf-8")

            scanner = FileScanner(ignore_dirs={"node_modules"}, ignore_extensions={".log"})
            files = scanner.scan(root)

            self.assertEqual({f.name for f in files}, {"keep.txt"})

    def test_binary_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary_file = root / "blob.bin"
            binary_file.write_bytes(b"\x00\x01\x02\x03")

            scanner = FileScanner()
            files = scanner.scan(root)

            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].is_binary)


if __name__ == "__main__":
    unittest.main()
