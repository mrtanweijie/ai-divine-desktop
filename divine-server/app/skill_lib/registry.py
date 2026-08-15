"""Runtime skill registry used by the agent and skill pages."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from .parser import SkillMeta, _parse_skill
from .paths import _is_within, builtin_skills_dir, user_skills_dir

logger = logging.getLogger("divine.skills")

class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillMeta] = {}

    def refresh(
        self,
        project_root: Path | None = None,
        project_roots: list[Path] | None = None,
    ) -> list[dict[str, Any]]:
        roots: list[tuple[Path, str]] = []
        seen_projects: set[Path] = set()
        for root in project_roots or []:
            resolved = root.resolve()
            if resolved in seen_projects:
                continue
            seen_projects.add(resolved)
            roots.append((resolved / ".divine" / "skills", "project"))
        if project_root is not None:
            resolved = project_root.resolve()
            if resolved not in seen_projects:
                seen_projects.add(resolved)
                roots.append((resolved / ".divine" / "skills", "project"))
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

    def executable_skills(self) -> list[SkillMeta]:
        return [
            meta
            for meta in self._skills.values()
            if meta.type == "executable" and meta.script_path is not None
        ]

    def uninstall(
        self,
        name: str,
        project_root: Path | None = None,
        project_roots: list[Path] | None = None,
    ) -> dict[str, Any]:
        self.refresh(project_root, project_roots)
        meta = self._skills.get(name)
        if meta is None:
            raise KeyError(f"技能不存在: {name}")
        if meta.source == "builtin":
            raise PermissionError("内置技能不能卸载")
        allowed_roots = [user_skills_dir()]
        if project_root is not None:
            allowed_roots.append(project_root / ".divine" / "skills")
        for root in project_roots or []:
            allowed_roots.append(root / ".divine" / "skills")
        skill_dir = meta.dir.resolve()
        if not any(
            _is_within(root, skill_dir) for root in allowed_roots
        ):
            raise PermissionError("只能卸载用户级或项目级技能")
        shutil.rmtree(skill_dir)
        self.refresh(project_root)
        return {
            "ok": True,
            "name": name,
            "dir": str(skill_dir),
        }

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
        parts = [
            f"技能目录：{meta.dir}（运行本技能脚本时以该目录为工作目录）",
            meta.body,
        ]
        if meta.references_content:
            parts.append(
                "参考资料：\n" + meta.references_content
            )
        return "\n\n".join(part for part in parts if part)

skill_registry = SkillRegistry()
