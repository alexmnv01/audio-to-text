from pathlib import Path

from audio_to_text.errors.app_errors import InputValidationError
from audio_to_text.input_sources.validators import SUPPORTED_EXTENSIONS
from audio_to_text.models.job import BatchJobItem, ProcessingMode


class FolderSource:
    def build_items(self, folder: str, recursive: bool) -> list[BatchJobItem]:
        if not folder.strip():
            raise InputValidationError("Папка не указана.")
        base_path = Path(folder).expanduser()
        if not base_path.exists():
            raise InputValidationError("Указанная папка не существует.")
        if not base_path.is_dir():
            raise InputValidationError("Указанный путь не является папкой.")

        iterator = base_path.rglob("*") if recursive else base_path.glob("*")
        files = sorted(
            path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not files:
            raise InputValidationError("В папке нет подходящих аудиофайлов.")

        return [
            BatchJobItem(
                item_id=f"file-{index}",
                source_label=str(path),
                source_path=path,
                mode=ProcessingMode.FOLDER,
            )
            for index, path in enumerate(files, start=1)
        ]
