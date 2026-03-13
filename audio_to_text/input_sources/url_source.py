from pathlib import Path
from typing import Iterable

from audio_to_text.errors.app_errors import InputValidationError
from audio_to_text.input_sources.validators import validate_url
from audio_to_text.models.job import BatchJobItem, ProcessingMode


class UrlListSource:
    def build_items(self, raw_text: str) -> list[BatchJobItem]:
        urls = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not urls:
            raise InputValidationError("Список URL пуст.")
        items: list[BatchJobItem] = []
        for index, url in enumerate(urls, start=1):
            valid_url = validate_url(url)
            items.append(
                BatchJobItem(
                    item_id=f"url-{index}",
                    source_label=valid_url,
                    source_url=valid_url,
                    mode=ProcessingMode.URL_LIST,
                )
            )
        return items

    def load_from_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InputValidationError(
                f"Не удалось прочитать файл со списком URL: {exc}"
            ) from exc
