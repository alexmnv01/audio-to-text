from pathlib import Path
import time
from queue import Queue
import threading

from audio_to_text.downloader.http_downloader import HttpDownloader
from audio_to_text.errors.app_errors import AppError, DownloadError, EnvironmentError, OutputError, TranscriptionError
from audio_to_text.models.job import BatchJobItem, ProcessingMode
from audio_to_text.models.result import BatchItemResult
from audio_to_text.models.status import ItemStatus
from audio_to_text.output.reporting import BatchLogger
from audio_to_text.output.writer import TranscriptWriter
from audio_to_text.transcription.backend import FasterWhisperBackend


class BatchProcessor:
    def __init__(
        self,
        backend: FasterWhisperBackend,
        downloader: HttpDownloader,
        writer: TranscriptWriter,
        logger: BatchLogger | None = None,
        transcription_heartbeat_seconds: float = 5.0,
    ) -> None:
        self.backend = backend
        self.downloader = downloader
        self.writer = writer
        self.logger = logger
        self.transcription_heartbeat_seconds = transcription_heartbeat_seconds

    def process(
        self,
        items: list[BatchJobItem],
        output_dir: Path,
        language: str,
        existing_file_policy: str,
        event_queue: Queue,
        cancel_event: threading.Event,
    ) -> None:
        try:
            self.backend.ensure_ready()
            if self.logger:
                self.logger.info("Backend успешно инициализирован.")
        except (EnvironmentError, AppError) as exc:
            if self.logger:
                self.logger.error(f"Критическая ошибка инициализации backend: {exc}")
            event_queue.put(("critical_error", str(exc)))
            event_queue.put(("finished", False))
            return
        total = len(items)
        for index, item in enumerate(items, start=1):
            if cancel_event.is_set():
                if self.logger:
                    self.logger.info(f"{item.item_id}: обработка отменена до запуска элемента.")
                event_queue.put(("item_result", BatchItemResult(
                    item_id=item.item_id,
                    status=ItemStatus.CANCELLED,
                    message="Обработка отменена пользователем до запуска элемента.",
                    source_path=item.source_path,
                )))
                event_queue.put(("progress", index, total))
                continue
            event_queue.put(("item_update", item.item_id, ItemStatus.QUEUED, f"Элемент {index} из {total} поставлен в очередь."))
            try:
                if self.logger:
                    self.logger.info(f"{item.item_id}: старт обработки источника {item.source_label}")
                source_path = self._resolve_source(item, event_queue)
                if self.logger:
                    self.logger.info(f"{item.item_id}: источник готов: {source_path}")
                if cancel_event.is_set():
                    if self.logger:
                        self.logger.info(f"{item.item_id}: обработка отменена после подготовки источника.")
                    event_queue.put(("item_result", BatchItemResult(
                        item_id=item.item_id,
                        status=ItemStatus.CANCELLED,
                        message="Обработка отменена пользователем.",
                        source_path=source_path,
                    )))
                    continue
                event_queue.put(("item_update", item.item_id, ItemStatus.PROCESSING, "Идет распознавание."))
                if self.logger:
                    self.logger.info(f"{item.item_id}: начата транскрибация.")
                heartbeat_stop = threading.Event()
                heartbeat_thread = threading.Thread(
                    target=self._emit_transcription_heartbeat,
                    kwargs={
                        "item_id": item.item_id,
                        "event_queue": event_queue,
                        "stop_event": heartbeat_stop,
                    },
                    daemon=True,
                )
                heartbeat_thread.start()
                try:
                    transcript = self.backend.transcribe(
                        source_path,
                        language,
                        progress_callback=lambda fraction, segment_text: self._handle_transcription_progress(
                            item_id=item.item_id,
                            fraction=fraction,
                            segment_text=segment_text,
                            event_queue=event_queue,
                        ),
                    )
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=0.2)
                if self.logger:
                    self.logger.info(f"{item.item_id}: транскрибация завершена, символов: {len(transcript)}")
                if cancel_event.is_set():
                    if self.logger:
                        self.logger.info(f"{item.item_id}: обработка отменена после распознавания.")
                    event_queue.put(("item_result", BatchItemResult(
                        item_id=item.item_id,
                        status=ItemStatus.CANCELLED,
                        message="Обработка отменена после распознавания. Результат не был сохранен.",
                        transcript_text=transcript,
                        source_path=source_path,
                    )))
                    continue
                event_queue.put(("item_text", item.item_id, transcript))
                event_queue.put(("item_update", item.item_id, ItemStatus.SAVING, "Сохраняется .txt файл."))
                if self.logger:
                    self.logger.info(f"{item.item_id}: начато сохранение результата.")
                output_path, message = self.writer.write(
                    output_dir=output_dir,
                    base_name=source_path.stem,
                    text=transcript,
                    policy=existing_file_policy,
                )
                status = ItemStatus.SKIPPED if output_path is None else ItemStatus.DONE
                if self.logger:
                    self.logger.info(
                        f"{item.item_id}: завершено со статусом {status.value}. {message}"
                    )
                event_queue.put(("item_result", BatchItemResult(
                    item_id=item.item_id,
                    status=status,
                    message=message,
                    transcript_text=transcript,
                    output_path=output_path,
                    source_path=source_path,
                )))
            except (DownloadError, TranscriptionError, OutputError, AppError) as exc:
                if self.logger:
                    self.logger.error(f"{item.item_id}: ошибка обработки: {exc}")
                event_queue.put(("item_result", BatchItemResult(
                    item_id=item.item_id,
                    status=ItemStatus.ERROR,
                    message=str(exc),
                    source_path=item.source_path,
                )))
            finally:
                event_queue.put(("progress", index, total))
        event_queue.put(("finished", cancel_event.is_set()))

    def _resolve_source(self, item: BatchJobItem, event_queue: Queue) -> Path:
        if item.mode == ProcessingMode.URL_LIST and item.source_url:
            event_queue.put(("item_update", item.item_id, ItemStatus.DOWNLOADING, "Скачивается файл по URL."))
            if self.logger:
                self.logger.info(f"{item.item_id}: начато скачивание {item.source_url}")
            return self.downloader.download(item.source_url)
        if item.source_path is None:
            raise AppError("Не удалось определить источник аудио.")
        return item.source_path

    def _handle_transcription_progress(
        self,
        item_id: str,
        fraction: float | None,
        segment_text: str,
        event_queue: Queue,
    ) -> None:
        preview = segment_text if len(segment_text) <= 80 else f"{segment_text[:77]}..."
        if self.logger:
            if fraction is None:
                self.logger.info(f"{item_id}: сегмент распознан: {preview}")
            else:
                percent = round(fraction * 100)
                self.logger.info(f"{item_id}: транскрибация {percent}%: {preview}")
        event_queue.put(("transcription_progress", item_id, fraction, preview))

    def _emit_transcription_heartbeat(
        self,
        item_id: str,
        event_queue: Queue,
        stop_event: threading.Event,
    ) -> None:
        started_at = time.monotonic()
        while not stop_event.wait(self.transcription_heartbeat_seconds):
            elapsed_seconds = int(time.monotonic() - started_at)
            if self.logger:
                self.logger.info(
                    f"{item_id}: транскрибация продолжается, прошло {elapsed_seconds} сек."
                )
            event_queue.put(("transcription_heartbeat", item_id, elapsed_seconds))
