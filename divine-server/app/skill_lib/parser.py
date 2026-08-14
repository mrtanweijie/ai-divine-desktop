"""SKILL.md parsing and SkillMeta construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import (
    MAX_REFERENCE_FILE_CHARS,
    MAX_REFERENCE_TOTAL_CHARS,
    MAX_SKILL_BODY_CHARS,
    _ENTRY_SCRIPT_CANDIDATES,
)

def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, text
    end = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if end is None:
        return {}, text
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, "\n".join(lines[end + 1 :])

def _load_reference_content(skill_dir: Path) -> tuple[str, list[str]]:
    ref_dir = skill_dir / "references"
    if not ref_dir.is_dir():
        return "", []
    parts: list[str] = []
    names: list[str] = []
    total = 0
    for path in sorted(ref_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(skill_dir)
        names.append(str(relative))
        if not content.strip():
            continue
        content = content[:MAX_REFERENCE_FILE_CHARS]
        remaining = MAX_REFERENCE_TOTAL_CHARS - total
        if remaining <= 0:
            break
        parts.append(f"[{relative}]\n{content[:remaining]}")
        total += min(len(content), remaining)
    return "\n\n".join(parts), names

def _description_from_markdown(frontmatter: dict[str, Any], body: str) -> str:
    description = str(frontmatter.get("description") or "").strip()
    if description:
        return description[:200]
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if stripped:
            return stripped[:200]
    return ""

def _detect_script_path(
    skill_dir: Path, frontmatter: dict[str, Any]
) -> tuple[Path | None, str]:
    explicit = str(frontmatter.get("script") or "").strip()
    if explicit:
        candidate = (skill_dir / explicit).resolve()
        try:
            candidate.relative_to(skill_dir.resolve())
        except ValueError:
            candidate = None
        if candidate is not None and candidate.is_file():
            mode = str(frontmatter.get("script_mode") or "").strip().lower()
            if mode not in {"json", "cli"}:
                mode = "json" if candidate.name == "script.py" else "cli"
            return candidate, mode

    root_script = skill_dir / "script.py"
    if root_script.is_file():
        return root_script, "json"

    for relative in _ENTRY_SCRIPT_CANDIDATES:
        candidate = skill_dir / relative
        if candidate.is_file():
            return candidate, "cli"

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        scripts = sorted(
            path
            for path in scripts_dir.iterdir()
            if path.is_file() and path.suffix == ".py"
        )
        if len(scripts) == 1:
            return scripts[0], "cli"
    return None, "cli"

class SkillMeta:
    name: str
    description: str
    type: str
    source: str
    path: Path
    dir: Path
    version: str = "0.0.0"
    dependencies: list[str] = field(default_factory=list)
    body: str = ""
    references_content: str = ""
    reference_files: list[str] = field(default_factory=list)
    script_path: Path | None = None
    script_mode: str = "cli"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "source": self.source,
            "version": self.version,
            "path": str(self.path),
            "dependencies": self.dependencies,
            "body": self.body,
            "references": self.reference_files,
            "script_path": str(self.script_path) if self.script_path else None,
            "script_mode": self.script_mode,
        }

def _parse_skill(skill_dir: Path, source: str) -> SkillMeta | None:
    md_path = skill_dir / "SKILL.md"
    if not md_path.is_file():
        return None
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    frontmatter, body = _split_frontmatter(text)
    name = str(frontmatter.get("name") or skill_dir.name).strip()
    if not name:
        return None
    description = str(frontmatter.get("description") or "").strip()
    type_name = str(frontmatter.get("type") or "knowledge").strip().lower()
    if type_name not in {"knowledge", "executable", "mcp"}:
        type_name = "knowledge"
    script_path, script_mode = _detect_script_path(skill_dir, frontmatter)
    if type_name == "knowledge" and script_path is not None:
        type_name = "executable"
    version = str(frontmatter.get("version") or "0.0.0").strip()
    dependencies: list[str] = []
    requirements = skill_dir / "requirements.txt"
    if requirements.is_file():
        try:
            dependencies = [
                line.strip()
                for line in requirements.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        except (OSError, UnicodeDecodeError):
            dependencies = []
    references_content, reference_files = _load_reference_content(skill_dir)
    return SkillMeta(
        name=name,
        description=description,
        type=type_name,
        source=source,
        path=md_path,
        dir=skill_dir,
        version=version,
        dependencies=dependencies,
        body=body.strip()[:MAX_SKILL_BODY_CHARS],
        references_content=references_content,
        reference_files=reference_files,
        script_path=script_path,
        script_mode=script_mode,
    )
