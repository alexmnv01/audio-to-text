import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_to_text.downloader.http_downloader import HttpDownloader
from audio_to_text.errors.app_errors import DownloadError


class FakeResponse:
    def __init__(self, status_code: int = 200, headers: dict | None = None, chunks: list[bytes] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or [b"audio"]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 0):  # noqa: ARG002
        for chunk in self._chunks:
            yield chunk


class DownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.downloader = HttpDownloader()
        self.downloader.temp_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("audio_to_text.downloader.http_downloader.requests.get")
    def test_download_saves_supported_audio_file(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(
            headers={"Content-Type": "audio/mpeg"},
            chunks=[b"part1", b"part2"],
        )

        path = self.downloader.download("https://example.com/music.mp3")

        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".mp3")
        self.assertEqual(path.read_bytes(), b"part1part2")

    @patch("audio_to_text.downloader.http_downloader.requests.get")
    def test_download_rejects_unsupported_content_type(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(headers={"Content-Type": "text/html"})

        with self.assertRaises(DownloadError):
            self.downloader.download("https://example.com/file.mp3")

    @patch("audio_to_text.downloader.http_downloader.requests.get")
    def test_download_requires_detectable_extension(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(headers={"Content-Type": ""})

        with self.assertRaises(DownloadError):
            self.downloader.download("https://example.com/download")
