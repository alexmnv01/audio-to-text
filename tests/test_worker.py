import threading
import tempfile
import unittest
from pathlib import Path
from queue import Queue

from audio_to_text.errors.app_errors import DownloadError, EnvironmentError
from audio_to_text.models.job import BatchJobItem, ProcessingMode
from audio_to_text.models.status import ItemStatus
from audio_to_text.transcription.worker import BatchProcessor


class FakeBackend:
    def __init__(self, *, fail_ready: bool = False, transcribe_map: dict[str, str] | None = None) -> None:
        self.fail_ready = fail_ready
        self.transcribe_map = transcribe_map or {}
        self.transcribed_paths: list[Path] = []

    def ensure_ready(self) -> None:
        if self.fail_ready:
            raise EnvironmentError("backend init failed")

    def transcribe(self, audio_path: Path, language: str, progress_callback=None) -> str:  # noqa: ARG002
        self.transcribed_paths.append(audio_path)
        if progress_callback is not None:
            progress_callback(0.5, f"segment:{audio_path.stem}")
        return self.transcribe_map.get(audio_path.name, f"text:{audio_path.stem}")


class FakeDownloader:
    def __init__(self, *, mapping: dict[str, Path] | None = None, failing_urls: set[str] | None = None) -> None:
        self.mapping = mapping or {}
        self.failing_urls = failing_urls or set()
        self.downloaded_urls: list[str] = []

    def download(self, url: str) -> Path:
        self.downloaded_urls.append(url)
        if url in self.failing_urls:
            raise DownloadError("download failed")
        return self.mapping[url]


class FakeWriter:
    def __init__(self, *, hook=None) -> None:
        self.hook = hook
        self.calls: list[tuple[Path, str, str, str]] = []

    def write(self, output_dir: Path, base_name: str, text: str, policy: str) -> tuple[Path | None, str]:
        self.calls.append((output_dir, base_name, text, policy))
        if self.hook is not None:
            self.hook(output_dir, base_name, text, policy)
        return output_dir / f"{base_name}.txt", "saved"


class BatchProcessorTests(unittest.TestCase):
    def _drain_queue(self, queue: Queue) -> list[tuple]:
        events: list[tuple] = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return events

    def test_process_emits_success_events_for_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            source_path = output_dir / "sample.mp3"
            source_path.write_bytes(b"audio")
            item = BatchJobItem(
                item_id="file-1",
                source_label=str(source_path),
                source_path=source_path,
                mode=ProcessingMode.FOLDER,
            )
            backend = FakeBackend(transcribe_map={"sample.mp3": "decoded text"})
            writer = FakeWriter()
            processor = BatchProcessor(backend=backend, downloader=FakeDownloader(), writer=writer)
            queue = Queue()

            processor.process(
                items=[item],
                output_dir=output_dir,
                language="ru",
                existing_file_policy="overwrite",
                event_queue=queue,
                cancel_event=threading.Event(),
            )

            events = self._drain_queue(queue)
            event_kinds = [event[0] for event in events]
            self.assertIn("item_text", event_kinds)
            self.assertIn("item_result", event_kinds)
            self.assertIn("transcription_progress", event_kinds)
            self.assertEqual(events[-1], ("finished", False))
            result_event = next(event for event in events if event[0] == "item_result")
            self.assertEqual(result_event[1].status, ItemStatus.DONE)
            self.assertEqual(result_event[1].transcript_text, "decoded text")
            self.assertEqual(writer.calls[0][1], "sample")

    def test_process_continues_after_item_download_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            ok_file = output_dir / "ok.wav"
            ok_file.write_bytes(b"audio")
            items = [
                BatchJobItem(
                    item_id="url-1",
                    source_label="https://example.com/bad.mp3",
                    source_url="https://example.com/bad.mp3",
                    mode=ProcessingMode.URL_LIST,
                ),
                BatchJobItem(
                    item_id="file-2",
                    source_label=str(ok_file),
                    source_path=ok_file,
                    mode=ProcessingMode.FOLDER,
                ),
            ]
            processor = BatchProcessor(
                backend=FakeBackend(transcribe_map={"ok.wav": "ok text"}),
                downloader=FakeDownloader(failing_urls={"https://example.com/bad.mp3"}),
                writer=FakeWriter(),
            )
            queue = Queue()

            processor.process(
                items=items,
                output_dir=output_dir,
                language="auto",
                existing_file_policy="overwrite",
                event_queue=queue,
                cancel_event=threading.Event(),
            )

            events = self._drain_queue(queue)
            results = [event[1] for event in events if event[0] == "item_result"]
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].status, ItemStatus.ERROR)
            self.assertEqual(results[1].status, ItemStatus.DONE)
            self.assertEqual(events[-1], ("finished", False))

    def test_process_marks_remaining_items_cancelled_after_cancel_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first = output_dir / "first.mp3"
            second = output_dir / "second.mp3"
            first.write_bytes(b"audio")
            second.write_bytes(b"audio")
            items = [
                BatchJobItem(
                    item_id="file-1",
                    source_label=str(first),
                    source_path=first,
                    mode=ProcessingMode.FOLDER,
                ),
                BatchJobItem(
                    item_id="file-2",
                    source_label=str(second),
                    source_path=second,
                    mode=ProcessingMode.FOLDER,
                ),
            ]
            cancel_event = threading.Event()

            def cancel_on_first_write(_output_dir: Path, _base_name: str, _text: str, _policy: str) -> None:
                cancel_event.set()

            processor = BatchProcessor(
                backend=FakeBackend(),
                downloader=FakeDownloader(),
                writer=FakeWriter(hook=cancel_on_first_write),
            )
            queue = Queue()

            processor.process(
                items=items,
                output_dir=output_dir,
                language="en",
                existing_file_policy="overwrite",
                event_queue=queue,
                cancel_event=cancel_event,
            )

            events = self._drain_queue(queue)
            results = [event[1] for event in events if event[0] == "item_result"]
            self.assertEqual(results[0].status, ItemStatus.DONE)
            self.assertEqual(results[1].status, ItemStatus.CANCELLED)
            self.assertEqual(events[-1], ("finished", True))

    def test_process_emits_critical_error_when_backend_init_fails(self) -> None:
        processor = BatchProcessor(
            backend=FakeBackend(fail_ready=True),
            downloader=FakeDownloader(),
            writer=FakeWriter(),
        )
        queue = Queue()

        processor.process(
            items=[],
            output_dir=Path("."),
            language="auto",
            existing_file_policy="overwrite",
            event_queue=queue,
            cancel_event=threading.Event(),
        )

        events = self._drain_queue(queue)
        self.assertEqual(events[0][0], "critical_error")
        self.assertIn("backend init failed", events[0][1])
        self.assertEqual(events[1], ("finished", False))
