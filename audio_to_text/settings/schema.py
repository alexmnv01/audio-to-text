from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from audio_to_text.models.job import ExistingFilePolicy


LanguageOption = str


@dataclass(slots=True)
class AppSettings:
    input_folder: str = ""
    output_folder: str = ""
    default_language: LanguageOption = "auto"
    model_name: str = "small"
    recursive: bool = False
    existing_file_policy: str = ExistingFilePolicy.RENAME.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        return cls(
            input_folder=str(data.get("input_folder", "")),
            output_folder=str(data.get("output_folder", "")),
            default_language=str(data.get("default_language", "auto")),
            model_name=str(data.get("model_name", "small")),
            recursive=bool(data.get("recursive", False)),
            existing_file_policy=str(
                data.get("existing_file_policy", ExistingFilePolicy.RENAME.value)
            ),
        )

    @property
    def input_folder_path(self) -> Path | None:
        return Path(self.input_folder) if self.input_folder else None

    @property
    def output_folder_path(self) -> Path | None:
        return Path(self.output_folder) if self.output_folder else None
