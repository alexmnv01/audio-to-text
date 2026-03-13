from pathlib import Path
from urllib.parse import urlparse

from audio_to_text.errors.app_errors import InputValidationError

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm"}


def validate_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise InputValidationError("Список URL пуст.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InputValidationError(f"Некорректный URL: {cleaned}")
    return cleaned


def ensure_supported_file(path: Path) -> Path:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InputValidationError(f"Формат файла не поддерживается: {path.name}")
    return path
