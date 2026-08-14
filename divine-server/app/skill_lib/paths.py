"""Skill directory locations and shared path helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

MAX_SKILL_BODY_CHARS = 12000

MAX_REFERENCE_FILE_CHARS = 4000

MAX_REFERENCE_TOTAL_CHARS = 20000

MAX_IMPORT_PREVIEW_CHARS = 2000

MAX_IMPORTED_SKILL_SIZE = 10 * 1024 * 1024

_ENTRY_SCRIPT_CANDIDATES = (
    "scripts/main.py",
    "scripts/run.py",
    "scripts/entrypoint.py",
)

def user_skills_dir() -> Path:
    configured = os.getenv("DIVINE_SKILLS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".divine" / "skills"

def builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"

def skills_target_dir(project_root: Path, target: str = "project") -> Path:
    if target == "user":
        return user_skills_dir()
    return project_root / ".divine" / "skills"

def _sanitize_skill_name(value: str, fallback: str = "") -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", value.strip()).strip(".-")
    if not cleaned and fallback:
        cleaned = re.sub(r"[^\w.-]+", "-", fallback.strip()).strip(".-")
    return cleaned or "skill"

def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False
