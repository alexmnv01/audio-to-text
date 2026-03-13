from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from audio_to_text.models.status import ItemStatus


@dataclass(slots=True)
class BatchItemResult:
    item_id: str
    status: ItemStatus
    message: str
    transcript_text: str = ""
    output_path: Optional[Path] = None
    source_path: Optional[Path] = None
