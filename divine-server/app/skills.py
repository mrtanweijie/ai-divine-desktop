from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("divine.skills")

MAX_SKILL_BODY_CHARS = 12000
MAX_REFERENCE_FILE_CHARS = 4000
MAX_REFERENCE_TOTAL_CHARS = 20000
MAX_IMPORT_PREVIEW_CHARS = 2000
MAX_IMPORTED_SKILL_SIZE = 10 * 1024 * 1024


class SkillMigrationError(RuntimeError):
    pass


def user_skills_dir() -> Path:
    configured = os.getenv("DIVINE_SKILLS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".divine" / "skills"


def builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


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


def skills_target_dir(project_root: Path, target: str = "project") -> Path:
    if target == "user":
        return user_skills_dir()
    return project_root / ".divine" / "skills"


def _sanitize_skill_name(value: str, fallback: str = "") -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", value.strip()).strip(".-")
    if not cleaned and fallback:
        cleaned = re.sub(r"[^\w.-]+", "-", fallback.strip()).strip(".-")
    return cleaned or "skill"


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


def _import_source_roots(
    project_root: Path,
) -> list[tuple[Path, str]]:
    home = Path.home()
    roots = [
        (home / ".claude" / "skills", "claude"),
        (project_root / ".claude" / "skills", "claude"),
        (home / ".qoder" / "skills", "qoder"),
        (project_root / ".qoder" / "skills", "qoder"),
        (home / ".qoderwork" / "skills", "qoder"),
        (project_root / ".qoderwork" / "skills", "qoder"),
        (project_root / ".cursor" / "skills", "cursor"),
        (project_root / ".cursor" / "rules", "cursor"),
    ]
    return [(root, tool) for root, tool in roots if root.is_dir()]


def _candidate_preview(path: Path, kind: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    _, body = _split_frontmatter(text)
    body = body.strip()
    if not body:
        body = text.strip()
    return body[:MAX_IMPORT_PREVIEW_CHARS]


def discover_importable_skills(
    project_root: Path,
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for root, source_tool in _import_source_roots(project_root):
        if root.name == "rules":
            for md_path in sorted(root.rglob("*.mdc")):
                if not md_path.is_file():
                    continue
                try:
                    text = md_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                frontmatter, body = _split_frontmatter(text)
                name = _sanitize_skill_name(
                    str(frontmatter.get("name") or md_path.stem),
                    md_path.stem,
                )
                key = (source_tool, name)
                candidates[key] = {
                    "name": name,
                    "source_tool": source_tool,
                    "kind": "cursor_rule",
                    "source_path": str(md_path),
                    "source_dir": str(md_path.parent),
                    "description": _description_from_markdown(
                        frontmatter, body
                    ),
                    "preview": _candidate_preview(md_path, "cursor_rule"),
                }
            continue

        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            md_path = skill_dir / "SKILL.md"
            if not md_path.is_file():
                continue
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            frontmatter, body = _split_frontmatter(text)
            name = _sanitize_skill_name(
                str(frontmatter.get("name") or skill_dir.name),
                skill_dir.name,
            )
            key = (source_tool, name)
            candidates[key] = {
                "name": name,
                "source_tool": source_tool,
                "kind": "skill_dir",
                "source_path": str(md_path),
                "source_dir": str(skill_dir),
                "description": _description_from_markdown(
                    frontmatter, body
                ),
                "preview": _candidate_preview(md_path, "skill_dir"),
            }

    result: list[dict[str, Any]] = []
    for (source_tool, name), candidate in candidates.items():
        target_dir = skills_target_dir(project_root)
        existing = (target_dir / name).exists()
        result.append(
            {
                **candidate,
                "existing": existing,
                "target": "project",
            }
        )
    return result


def find_importable_skill(
    project_root: Path,
    name: str,
    source_tool: str | None = None,
) -> dict[str, Any] | None:
    for candidate in discover_importable_skills(project_root):
        if candidate["name"] != name:
            continue
        if source_tool and candidate["source_tool"] != source_tool:
            continue
        return candidate
    return None


def _copy_skill_dir(source: Path, destination: Path) -> list[str]:
    total_size = 0
    copied: list[str] = []
    for dirpath, dirnames, filenames in os.walk(
        source, followlinks=False
    ):
        dirnames[:] = [
            name
            for name in dirnames
            if not (Path(dirpath) / name).is_symlink()
        ]
        relative = Path(dirpath).relative_to(source)
        target_dir = destination / relative if str(relative) != "." else destination
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            src_path = Path(dirpath) / filename
            if src_path.is_symlink():
                continue
            try:
                total_size += src_path.stat().st_size
            except OSError:
                continue
            if total_size > MAX_IMPORTED_SKILL_SIZE:
                raise SkillMigrationError("技能目录过大，已停止迁移")
            dst_path = target_dir / filename
            shutil.copy2(src_path, dst_path)
            copied.append(str(dst_path.relative_to(destination)))
    return copied


def _cursor_rule_skill_text(
    md_path: Path, name: str, description: str
) -> str:
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillMigrationError(f"读取 Cursor 规则失败: {exc}") from exc
    frontmatter, body = _split_frontmatter(text)
    body = body.strip() or text.strip()
    meta: dict[str, Any] = {
        "name": name,
        "description": description or "从 Cursor rules 迁移的规则",
        "source": "cursor-rule",
    }
    for key in ("globs", "alwaysApply", "ignore"):
        if frontmatter.get(key) is not None:
            meta[key] = frontmatter[key]
    frontmatter_text = yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False
    ).strip()
    return f"---\n{frontmatter_text}\n---\n\n{body}\n"


def migrate_skill(
    project_root: Path,
    name: str,
    source_tool: str | None = None,
    target: str = "project",
) -> dict[str, Any]:
    candidate = find_importable_skill(project_root, name, source_tool)
    if candidate is None:
        raise SkillMigrationError(
            f"未找到可迁移技能 {name}，请先调用 discover_importable_skills"
        )

    target_dir = skills_target_dir(project_root, target)
    destination = target_dir / str(candidate["name"])
    if destination.exists():
        raise SkillMigrationError(f"目标目录已存在: {destination}")
    target_dir.mkdir(parents=True, exist_ok=True)

    if candidate["kind"] == "cursor_rule":
        destination.mkdir()
        skill_text = _cursor_rule_skill_text(
            Path(str(candidate["source_path"])),
            str(candidate["name"]),
            str(candidate["description"]),
        )
        (destination / "SKILL.md").write_text(
            skill_text, encoding="utf-8"
        )
        copied = ["SKILL.md"]
    else:
        copied = _copy_skill_dir(
            Path(str(candidate["source_dir"])), destination
        )

    skill_registry.refresh(project_root)
    return {
        "ok": True,
        "name": str(candidate["name"]),
        "source_tool": str(candidate["source_tool"]),
        "kind": str(candidate["kind"]),
        "target": target,
        "target_path": str(destination),
        "files": copied,
    }


@dataclass
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
    if type_name == "knowledge" and (skill_dir / "script.py").is_file():
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
    )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillMeta] = {}

    def refresh(self, project_root: Path | None = None) -> list[dict[str, Any]]:
        roots: list[tuple[Path, str]] = []
        if project_root is not None:
            roots.append((project_root / ".divine" / "skills", "project"))
        roots.append((user_skills_dir(), "user"))
        roots.append((builtin_skills_dir(), "builtin"))

        skills: dict[str, SkillMeta] = {}
        for root, source in reversed(roots):
            if not root.is_dir():
                continue
            for skill_dir in sorted(root.iterdir()):
                if not skill_dir.is_dir():
                    continue
                meta = _parse_skill(skill_dir, source)
                if meta is not None:
                    skills[meta.name] = meta
        self._skills = skills
        logger.info(
            "skills refreshed count=%d project_root=%s",
            len(skills),
            project_root,
        )
        return self.list()

    def list(self) -> list[dict[str, Any]]:
        return [meta.as_dict() for meta in self._skills.values()]

    def get(self, name: str) -> SkillMeta | None:
        return self._skills.get(name)

    def knowledge_skills(self) -> list[SkillMeta]:
        return [
            meta
            for meta in self._skills.values()
            if meta.type == "knowledge"
        ]

    def load(self, name: str) -> str:
        meta = self._skills.get(name)
        if meta is None:
            return (
                '{"error": "技能不存在: '
                + name
                + '，可用技能：'
                + ", ".join(sorted(self._skills))
                + '"}'
            )
        parts = [meta.body]
        if meta.references_content:
            parts.append(
                "参考资料：\n" + meta.references_content
            )
        return "\n\n".join(part for part in parts if part)


skill_registry = SkillRegistry()
