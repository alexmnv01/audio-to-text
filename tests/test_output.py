import tempfile
import unittest
from pathlib import Path

from audio_to_text.errors.app_errors import OutputError
from audio_to_text.output.naming import sanitize_filename, unique_path
from audio_to_text.output.writer import TranscriptWriter


class NamingTests(unittest.TestCase):
    def test_sanitize_filename_replaces_invalid_characters(self) -> None:
        result = sanitize_filename('bad<>:"/\\\\|?*name')

        self.assertEqual(result, "bad_name")

    def test_unique_path_appends_suffix_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.txt"
            path.write_text("x", encoding="utf-8")

            candidate = unique_path(path)

        self.assertEqual(candidate.name, "result_1.txt")


class TranscriptWriterTests(unittest.TestCase):
    def test_write_creates_text_file(self) -> None:
        writer = TranscriptWriter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            output_path, message = writer.write(output_dir, "sample", "hello", "overwrite")

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "hello")
            self.assertEqual(message, "Результат сохранен.")

    def test_write_skips_existing_file_when_policy_is_skip(self) -> None:
        writer = TranscriptWriter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing = output_dir / "sample.txt"
            existing.write_text("old", encoding="utf-8")

            output_path, message = writer.write(output_dir, "sample", "new", "skip")

            self.assertIsNone(output_path)
            self.assertIn("пропущен", message.lower())
            self.assertEqual(existing.read_text(encoding="utf-8"), "old")

    def test_write_raises_for_empty_text(self) -> None:
        writer = TranscriptWriter()
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(OutputError):
                writer.write(Path(temp_dir), "sample", "   ", "overwrite")
