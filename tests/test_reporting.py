import json
import tempfile
import unittest
from pathlib import Path

from audio_to_text.output.reporting import BatchLogger, BatchReportWriter, ReportItem


class ReportingTests(unittest.TestCase):
    def test_batch_report_writer_creates_json_report(self) -> None:
        writer = BatchReportWriter()
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = writer.write_report(
                destination=Path(temp_dir),
                mode="folder",
                language="ru",
                items=[
                    ReportItem(
                        item_id="file-1",
                        source_label="a.mp3",
                        status="done",
                        message="ok",
                        output_path="a.txt",
                    )
                ],
            )

            payload = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["mode"], "folder")
        self.assertEqual(payload["language"], "ru")
        self.assertEqual(payload["items"][0]["status"], "done")

    def test_batch_logger_writes_log_file(self) -> None:
        logger = BatchLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = logger.start(Path(temp_dir))
            logger.info("step 1")
            logger.error("step 2")

            content = log_path.read_text(encoding="utf-8")

        self.assertIn("Лог пакетной обработки создан", content)
        self.assertIn("[INFO] step 1", content)
        self.assertIn("[ERROR] step 2", content)
