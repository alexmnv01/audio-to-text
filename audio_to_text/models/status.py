from enum import Enum


class ItemStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    SAVING = "saving"
    DONE = "done"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    ERROR = "error"
