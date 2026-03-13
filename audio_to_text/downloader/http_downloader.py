import mimetypes
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

from audio_to_text.errors.app_errors import DownloadError
from audio_to_text.input_sources.validators import SUPPORTED_EXTENSIONS
from audio_to_text.output.naming import sanitize_filename

ALLOWED_CONTENT_TYPES = (
    "audio/",
    "video/",
    "application/octet-stream",
)


class HttpDownloader:
    def __init__(self, timeout_seconds: int = 60) -> None:
        self.timeout_seconds = timeout_seconds
        self.temp_dir = Path(tempfile.gettempdir()) / "audio_to_text_downloads"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str) -> Path:
        parsed = urlparse(url)
        target_name = Path(parsed.path).name or "downloaded_audio"
        suffix = Path(target_name).suffix.lower()
        if suffix and suffix not in SUPPORTED_EXTENSIONS:
            raise DownloadError("URL не указывает на поддерживаемый аудиофайл.")

        try:
            response = requests.get(url, stream=True, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DownloadError(f"Ошибка скачивания: {exc}") from exc

        content_type = response.headers.get("Content-Type", "")
        normalized_content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        guessed_ext = mimetypes.guess_extension(normalized_content_type)
        if not suffix and guessed_ext:
            suffix = guessed_ext
        if normalized_content_type and not normalized_content_type.startswith(ALLOWED_CONTENT_TYPES):
            raise DownloadError(
                f"Сервер вернул неподдерживаемый тип данных: {normalized_content_type}"
            )
        if suffix and suffix not in SUPPORTED_EXTENSIONS:
            raise DownloadError("Загруженный файл не является поддерживаемым аудио или видео.")

        if not suffix:
            raise DownloadError(
                "Не удалось определить формат скачанного файла. Укажите URL с расширением аудиофайла."
            )

        safe_stem = sanitize_filename(Path(target_name).stem or "downloaded_audio")
        unique_name = f"{safe_stem}_{uuid.uuid4().hex[:8]}{suffix}"
        destination = self.temp_dir / unique_name

        try:
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
        except OSError as exc:
            raise DownloadError(f"Не удалось сохранить скачанный файл: {exc}") from exc

        if not destination.exists() or destination.stat().st_size == 0:
            destination.unlink(missing_ok=True)
            raise DownloadError("Скачанный файл пуст.")
        if destination.suffix.lower() not in SUPPORTED_EXTENSIONS:
            destination.unlink(missing_ok=True)
            raise DownloadError("Скачанный файл не является поддерживаемым аудиофайлом.")
        return destination
