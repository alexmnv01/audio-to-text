from pathlib import Path

from audio_to_text.errors.app_errors import OutputError
from audio_to_text.models.job import ExistingFilePolicy
from audio_to_text.output.naming import sanitize_filename, unique_path


class TranscriptWriter:
    def write(
        self,
        output_dir: Path,
        base_name: str,
        text: str,
        policy: str,
    ) -> tuple[Path | None, str]:
        if not text.strip():
            raise OutputError("Нельзя сохранить пустой результат.")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputError(f"Папка результатов недоступна: {exc}") from exc

        filename = f"{sanitize_filename(base_name)}.txt"
        output_path = output_dir / filename
        policy_enum = ExistingFilePolicy(policy)

        if output_path.exists():
            if policy_enum == ExistingFilePolicy.SKIP:
                return None, "Файл результата уже существует, элемент пропущен."
            if policy_enum == ExistingFilePolicy.RENAME:
                output_path = unique_path(output_path)

        try:
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise OutputError(f"Не удалось сохранить результат: {exc}") from exc
        return output_path, "Результат сохранен."
