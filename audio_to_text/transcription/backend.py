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
                    build_model_init_error_message(self.model_name, exc)
                ) from exc
        return self._model


def build_model_init_error_message(model_name: str, exc: Exception) -> str:
    raw_message = str(exc)
    normalized = raw_message.lower()
    details = [f"Не удалось инициализировать модель '{model_name}'."]

    if "certificate verify failed" in normalized:
        details.append(
            "Не удалось безопасно скачать модель по HTTPS. Проверьте дату, время и часовой пояс Windows, "
            "затем повторите попытку."
        )
        if "certificate is not yet valid" in normalized:
            details.append(
                "Судя по тексту ошибки, системное время на компьютере отстает или указано неверно."
            )

    if "cannot find the appropriate snapshot folder" in normalized or "trying to locate the files on the hub" in normalized:
        details.append(
            "Локальная копия модели не найдена. Нужен либо успешный первый запуск с доступом к интернету для "
            "скачивания модели, либо заранее подготовленный локальный кэш Hugging Face."
        )

    if len(details) == 1:
        details.append(raw_message)
    else:
        details.append(f"Техническая причина: {raw_message}")
    return " ".join(details)
