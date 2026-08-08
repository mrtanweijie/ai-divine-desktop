from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def is_image_path(value: str | Path) -> bool:
    return Path(value).suffix.lower() in IMAGE_EXTENSIONS
