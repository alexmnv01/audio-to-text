import re
from pathlib import Path


def sanitize_filename(name: str, fallback: str = "transcript") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", name).strip(" .")
    return cleaned or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
