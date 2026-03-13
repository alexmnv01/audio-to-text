import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_to_text.settings.schema import AppSettings
from audio_to_text.transcription.environment import EnvironmentChecker


class EnvironmentCheckerTests(unittest.TestCase):
    @patch("audio_to_text.transcription.environment.shutil.which", return_value=None)
    @patch("audio_to_text.transcription.environment.WhisperModel", None)
    def test_check_reports_missing_backend_and_ffmpeg(self, _mock_which) -> None:
        checker = EnvironmentChecker(app_root=Path.cwd())

        report = checker.check(AppSettings())

        self.assertFalse(report.ready)
        self.assertEqual(len(report.issues), 2)

    @patch("audio_to_text.transcription.environment.shutil.which", return_value="ffmpeg")
    def test_check_reports_unwritable_output_folder(self, _mock_which) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_path = Path(temp_dir) / "not_a_dir.txt"
            bad_path.write_text("x", encoding="utf-8")
            checker = EnvironmentChecker(app_root=Path.cwd())

            report = checker.check(AppSettings(output_folder=str(bad_path)))

        self.assertFalse(report.ready)
        self.assertIn("не на папку", " ".join(report.issues).lower())
