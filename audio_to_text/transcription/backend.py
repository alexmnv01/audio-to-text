from pathlib import Path
from typing import Optional

from audio_to_text.errors.app_errors import EnvironmentError, TranscriptionError

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None


LANGUAGE_MAP = {
    "auto": None,
    "ru": "ru",
    "en": "en",
}


class FasterWhisperBackend:
    def __init__(self, model_name: str = "small", compute_type: str = "int8") -> None:
        if WhisperModel is None:
            raise EnvironmentError(
                "Не установлен faster-whisper. Установите зависимость из requirements.txt."
            )
        self.model_name = model_name
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def ensure_ready(self) -> None:
        self._get_model()

    def transcribe(self, audio_path: Path, language: str) -> str:
        model = self._get_model()
        try:
            segments, _info = model.transcribe(
                str(audio_path),
                language=LANGUAGE_MAP.get(language, None),
                beam_size=5,
                vad_filter=True,
            )
        except Exception as exc:  # pragma: no cover
            raise TranscriptionError(f"Ошибка транскрибации: {exc}") from exc

        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not text:
            raise TranscriptionError("Распознавание завершилось пустым результатом.")
        return text

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            try:
                self._model = WhisperModel(self.model_name, compute_type=self.compute_type)
            except Exception as exc:  # pragma: no cover
                raise EnvironmentError(
                    f"Не удалось инициализировать модель '{self.model_name}': {exc}"
                ) from exc
        return self._model
