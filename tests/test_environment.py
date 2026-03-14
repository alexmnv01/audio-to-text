import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_to_text.settings.schema import AppSettings
from audio_to_text.transcription.backend import build_model_init_error_message
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

    @patch("audio_to_text.transcription.environment.shutil.which", return_value="ffmpeg")
    @patch("audio_to_text.transcription.environment.WhisperModel", side_effect=Exception(
        "Got: ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "certificate is not yet valid (_ssl.c:1000) "
        "An error happened while trying to locate the files on the Hub and we cannot find "
        "the appropriate snapshot folder for the specified revision on the local disk."
    ))
    def test_check_reports_model_download_certificate_error_as_issue(self, _mock_model, _mock_which) -> None:
        checker = EnvironmentChecker(app_root=Path.cwd())

        report = checker.check(AppSettings())

        self.assertFalse(report.ready)
        joined = " ".join(report.issues).lower()
        self.assertIn("часовой пояс windows", joined)
        self.assertIn("локальная копия модели не найдена", joined)


class BackendMessageTests(unittest.TestCase):
    def test_build_model_init_error_message_for_certificate_issue(self) -> None:
        error = Exception(
            "Got: ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "certificate is not yet valid (_ssl.c:1000)"
        )

        message = build_model_init_error_message("small", error)

        self.assertIn("Не удалось безопасно скачать модель", message)
        self.assertIn("системное время", message)
