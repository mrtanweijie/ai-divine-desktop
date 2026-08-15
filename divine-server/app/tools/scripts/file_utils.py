"""Shared output path helpers for generated files."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def unique_output_path(
    output_dir: Path,
    name: str,
    fallback: str,
    extension: str,
) -> Path:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(extension):
        cleaned += extension
    path = output_dir / cleaned
    if not path.exists():
        return path

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = path.stem
    candidate = output_dir / f"{stem}_{timestamp}{extension}"
    counter = 1
    while candidate.exists():
        candidate = output_dir / f"{stem}_{timestamp}_{counter}{extension}"
        counter += 1
    return candidate
