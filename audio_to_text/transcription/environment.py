import shutil
from dataclasses import dataclass, field
from pathlib import Path

from audio_to_text.settings.schema import AppSettings

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None


@dataclass(slots=True)
class EnvironmentReport:
    ready: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backend_name: str = "faster-whisper"
    model_name: str = "small"

    @property
    def summary(self) -> str:
        if self.ready:
            return "Окружение готово к работе."
        return "Окружение не готово. Исправьте найденные проблемы."


class EnvironmentChecker:
    def __init__(self, app_root: Path) -> None:
        self.app_root = app_root

    def check(self, settings: AppSettings) -> EnvironmentReport:
        issues: list[str] = []
        warnings: list[str] = []

        if WhisperModel is None:
            issues.append("Не найден backend faster-whisper. Установите зависимости проекта.")

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            issues.append("Не найден ffmpeg. Он обязателен для декодирования аудиофайлов.")

        if settings.output_folder:
            output_path = Path(settings.output_folder)
            if output_path.exists() and not output_path.is_dir():
                issues.append("Путь к папке результатов указывает не на папку.")
            elif output_path.exists() and not os_access_write(output_path):
                issues.append("Папка результатов недоступна для записи.")

        if not issues and WhisperModel is not None:
            try:
                WhisperModel("small", compute_type="int8")
            except Exception as exc:
                warnings.append(
                    "Модель small не удалось проверить заранее. "
                    f"Она будет загружена при первом запуске обработки: {exc}"
                )

        return EnvironmentReport(ready=not issues, issues=issues, warnings=warnings)


def os_access_write(path: Path) -> bool:
    try:
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
