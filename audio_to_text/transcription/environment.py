import shutil
from dataclasses import dataclass, field
import os
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
        model_name = settings.model_name or "small"

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
            if not is_model_available_locally(model_name):
                warnings.append(
                    f"Локальная модель '{model_name}' не найдена. Подготовьте модель заранее в локальном кэше "
                    "faster-whisper / Hugging Face, либо приложение попробует скачать её при первом запуске."
                )

        return EnvironmentReport(
            ready=not issues,
            issues=issues,
            warnings=warnings,
            model_name=model_name,
        )


def os_access_write(path: Path) -> bool:
    try:
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def is_model_available_locally(model_name: str) -> bool:
    return any(path.exists() for path in candidate_model_paths(model_name))


def candidate_model_paths(model_name: str) -> list[Path]:
    repo_name = f"models--Systran--faster-whisper-{model_name}"
    snapshot_paths = [
        cache_root / "hub" / repo_name / "snapshots"
        for cache_root in _candidate_cache_roots()
    ]
    return snapshot_paths


def _candidate_cache_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "HF_HUB_CACHE"):
        value = os.getenv(env_name, "").strip()
        if not value:
            continue
        path = Path(value)
        roots.append(path if env_name == "HF_HOME" else path.parent)

    home = Path.home()
    roots.extend(
        [
            home / ".cache" / "huggingface",
        ]
    )
    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        normalized = root.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_roots.append(normalized)
    return unique_roots
