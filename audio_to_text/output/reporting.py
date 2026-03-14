from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from audio_to_text.errors.app_errors import OutputError


@dataclass(slots=True)
class ReportItem:
    item_id: str
    source_label: str
    status: str
    message: str
    output_path: str = ""


class BatchReportWriter:
    def write_report(
        self,
        destination: Path,
        mode: str,
        language: str,
        items: list[ReportItem],
    ) -> Path:
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputError(f"Не удалось подготовить папку для отчета: {exc}") from exc

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = destination / f"batch_report_{timestamp}.json"
        payload = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "language": language,
            "items": [asdict(item) for item in items],
        }
        try:
            report_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise OutputError(f"Не удалось сохранить отчет: {exc}") from exc
        return report_path


class BatchLogger:
    def __init__(self) -> None:
        self.log_path: Path | None = None

    def start(self, destination: Path) -> Path:
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputError(f"Не удалось подготовить папку для логов: {exc}") from exc
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_path = destination / f"batch_{timestamp}.log"
        self._write_line("INFO", "Лог пакетной обработки создан.")
        return self.log_path

    def info(self, message: str) -> None:
        self._write_line("INFO", message)

    def error(self, message: str) -> None:
        self._write_line("ERROR", message)

    def _write_line(self, level: str, message: str) -> None:
        if self.log_path is None:
            return
        line = f"{datetime.now(timezone.utc).isoformat()} [{level}] {message}\n"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
