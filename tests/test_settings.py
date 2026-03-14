import json
import tempfile
import unittest
from pathlib import Path

from audio_to_text.errors.app_errors import ConfigurationError
from audio_to_text.settings.manager import SettingsManager
from audio_to_text.settings.schema import AppSettings


class SettingsManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = SettingsManager()
        self.manager.settings_dir = Path(self.temp_dir.name)
        self.manager.settings_path = self.manager.settings_dir / "settings.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_returns_defaults_when_file_is_missing(self) -> None:
        settings = self.manager.load()

        self.assertEqual(settings, AppSettings())

    def test_save_and_load_roundtrip(self) -> None:
        source = AppSettings(
            input_folder="C:/audio",
            output_folder="C:/output",
            default_language="ru",
            model_name="base",
            recursive=True,
            existing_file_policy="overwrite",
        )

        self.manager.save(source)
        loaded = self.manager.load()

        self.assertEqual(loaded, source)
        payload = json.loads(self.manager.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["output_folder"], "C:/output")
        self.assertEqual(payload["model_name"], "base")

    def test_load_raises_configuration_error_for_invalid_json(self) -> None:
        self.manager.settings_dir.mkdir(parents=True, exist_ok=True)
        self.manager.settings_path.write_text("{broken", encoding="utf-8")

        with self.assertRaises(ConfigurationError):
            self.manager.load()
