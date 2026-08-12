from __future__ import annotations

from pathlib import Path
from typing import Any

from ...github_skills import (
    install_skill_repo,
    preview_skill_repo,
)
from ...skills import SkillMigrationError
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool


@register_tool(
    "preview_skill_repo",
    "只读拉取 GitHub 仓库并解析其中的 SKILL.md，返回技能名称、描述和正文预览。"
    "用户给出 GitHub 地址想安装技能时，先调用本工具展示内容，不要直接安装。",
    {
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "GitHub 仓库地址，例如 https://github.com/owner/repo",
            },
            "ref": {
                "type": "string",
                "description": "可选分支、标签或 commit，默认使用仓库默认分支",
            },
        },
        "required": ["repo_url"],
    },
)
class PreviewSkillRepoAdapter(ToolAdapter):
    category = "skills"
    timeout = 60

    async def run(
        self, workspace: Any, arguments: dict[str, Any]
    ) -> ToolResult:
        repo_url = str(arguments.get("repo_url") or "").strip()
        ref = str(arguments.get("ref") or "").strip() or None
        try:
            info = await preview_skill_repo(repo_url, ref)
        except SkillMigrationError as exc:
            raise ToolExecutionError(str(exc)) from exc
        count = len(info.get("skills") or [])
        return ToolResult(
            success=True,
            message=f"仓库 {info.get('repo')} 找到 {count} 个技能",
            data=info,
        )


@register_tool(
    "install_skill",
    "把 GitHub 仓库中的 SKILL.md 技能安装到 AI Divine。"
    "默认安装到当前项目 .divine/skills，target 传 user 时安装到用户级目录。"
    "安装前系统会再次展示 SKILL.md 并请求确认；"
    "仓库包含多个技能时，skill_path 必须传 preview_skill_repo 返回的相对目录。",
    {
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "GitHub 仓库地址",
            },
            "skill_path": {
                "type": "string",
                "description": "preview_skill_repo 返回的相对目录，多技能仓库必填",
            },
            "ref": {
                "type": "string",
                "description": "可选分支、标签或 commit",
            },
            "target": {
                "type": "string",
                "enum": ["project", "user"],
                "description": "project 安装到当前项目，user 安装到用户级目录",
            },
        },
        "required": ["repo_url"],
    },
)
class InstallSkillAdapter(ToolAdapter):
    category = "skills"
    timeout = 120

    async def run(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> ToolResult:
        repo_url = str(arguments.get("repo_url") or "").strip()
        skill_path = str(arguments.get("skill_path") or "").strip() or None
        ref = str(arguments.get("ref") or "").strip() or None
        target = str(arguments.get("target") or "project").strip()
        if target not in {"project", "user"}:
            raise ToolExecutionError("target 只支持 project 或 user")
        try:
            result = await install_skill_repo(
                repo_url,
                workspace,
                skill_path=skill_path,
                ref=ref,
                target=target,
            )
        except SkillMigrationError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolResult(
            success=True,
            message=f"技能 {result['name']} 已安装",
            data=result,
        )
