from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# Formats the vision model can analyze: JPEG / PNG / GIF / WebP
# (deepseek-v4-flash-vision-exp and GLM vision both accept only these).
VISION_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def is_image_path(value: str | Path) -> bool:
    return Path(value).suffix.lower() in IMAGE_EXTENSIONS
