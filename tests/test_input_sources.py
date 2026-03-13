import tempfile
import unittest
from pathlib import Path

from audio_to_text.errors.app_errors import InputValidationError
from audio_to_text.input_sources.folder_source import FolderSource
from audio_to_text.input_sources.url_source import UrlListSource
from audio_to_text.models.job import ProcessingMode


class UrlListSourceTests(unittest.TestCase):
    def test_build_items_creates_items_for_each_valid_url(self) -> None:
        source = UrlListSource()

        items = source.build_items("https://example.com/a.mp3\n\nhttps://example.com/b.wav")

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].mode, ProcessingMode.URL_LIST)
        self.assertEqual(items[1].source_url, "https://example.com/b.wav")

    def test_build_items_raises_for_invalid_url(self) -> None:
        source = UrlListSource()

        with self.assertRaises(InputValidationError):
            source.build_items("notaurl")


class FolderSourceTests(unittest.TestCase):
    def test_build_items_reads_supported_files_only(self) -> None:
        source = FolderSource()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "first.mp3").write_bytes(b"data")
            (root / "second.txt").write_text("skip", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "third.wav").write_bytes(b"data")

            flat_items = source.build_items(str(root), recursive=False)
            recursive_items = source.build_items(str(root), recursive=True)

        self.assertEqual(len(flat_items), 1)
        self.assertEqual(len(recursive_items), 2)
        self.assertEqual(recursive_items[0].mode, ProcessingMode.FOLDER)

    def test_build_items_raises_when_no_supported_files(self) -> None:
        source = FolderSource()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "note.txt").write_text("x", encoding="utf-8")

            with self.assertRaises(InputValidationError):
                source.build_items(str(root), recursive=False)
