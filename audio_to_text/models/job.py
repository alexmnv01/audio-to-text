from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from audio_to_text.models.status import ItemStatus


class ProcessingMode(str, Enum):
    URL_LIST = "url_list"
    FOLDER = "folder"
    SINGLE_FILE = "single_file"


class ExistingFilePolicy(str, Enum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    RENAME = "rename"


@dataclass(slots=True)
class BatchJobItem:
    item_id: str
    source_label: str
    mode: ProcessingMode
    source_path: Optional[Path] = None
    source_url: Optional[str] = None
    status: ItemStatus = ItemStatus.QUEUED
    message: str = ""
    detected_name: str = ""
    transcript_text: str = ""
    output_path: Optional[Path] = None
    downloaded_path: Optional[Path] = None
    language: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)
