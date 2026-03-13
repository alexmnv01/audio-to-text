import json
import os
from pathlib import Path

from audio_to_text.errors.app_errors import ConfigurationError
from audio_to_text.settings.schema import AppSettings


class SettingsManager:
    def __init__(self) -> None:
        self.settings_dir = self._resolve_settings_dir()
        self.settings_path = self.settings_dir / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Не удалось загрузить настройки: {exc}"
            ) from exc
        return AppSettings.from_dict(raw)

    def save(self, settings: AppSettings) -> None:
        try:
            self.settings_dir.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(
                json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ConfigurationError(
                f"Не удалось сохранить настройки: {exc}"
            ) from exc

    @staticmethod
    def _resolve_settings_dir() -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "AudioToText"
        return Path.home() / ".audio_to_text"
