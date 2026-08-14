"""Discovery and migration of skills from other AI coding tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from .parser import _description_from_markdown, _split_frontmatter
from .paths import (
    MAX_IMPORT_PREVIEW_CHARS,
    MAX_IMPORTED_SKILL_SIZE,
    _sanitize_skill_name,
    skills_target_dir,
)
from .registry import skill_registry

class SkillMigrationError(RuntimeError):
    pass

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

def _migrate_candidate(
    project_root: Path,
    candidate: dict[str, Any],
    target: str,
) -> dict[str, Any]:
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

    return {
        "ok": True,
        "name": str(candidate["name"]),
        "source_tool": str(candidate["source_tool"]),
        "kind": str(candidate["kind"]),
        "target": target,
        "target_path": str(destination),
        "files": copied,
    }

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
    result = _migrate_candidate(project_root, candidate, target)
    skill_registry.refresh(project_root)
    return result

def migrate_skills(
    project_root: Path,
    names: list[str],
    source_tool: str | None = None,
    target: str = "project",
) -> dict[str, Any]:
    candidates = discover_importable_skills(project_root)
    migrated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        candidate = None
        for item in candidates:
            if item["name"] != name:
                continue
            if source_tool and item["source_tool"] != source_tool:
                continue
            candidate = item
            break
        if candidate is None:
            failed.append(
                {
                    "name": name,
                    "reason": (
                        f"未找到可迁移技能 {name}，"
                        "请先调用 discover_importable_skills"
                    ),
                }
            )
            continue
        try:
            result = _migrate_candidate(project_root, candidate, target)
            migrated.append(result)
        except SkillMigrationError as exc:
            message = str(exc)
            if "已存在" in message:
                skipped.append({"name": name, "reason": message})
            else:
                failed.append({"name": name, "reason": message})
    skill_registry.refresh(project_root)
    if not migrated and not skipped and not failed:
        raise SkillMigrationError("没有可迁移的技能名")
    ok = bool(migrated) or not failed
    return {
        "ok": ok,
        "requested": len(names),
        "migrated": migrated,
        "skipped": skipped,
        "failed": failed,
    }
