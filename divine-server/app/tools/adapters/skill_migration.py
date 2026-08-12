from __future__ import annotations

from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ...skills import (
    SkillMigrationError,
    discover_importable_skills,
    migrate_skill,
)


@register_tool(
    "discover_importable_skills",
    "扫描 Claude Code、Qoder、Cursor 等本地 AI 工具已安装的技能，"
    "返回可迁移到 AI Divine 的候选列表。仅读取，不修改任何文件。"
    "当用户提到迁移、导入或同步其他 AI 工具的技能时调用。",
    {
        "type": "object",
        "properties": {},
    },
)
class DiscoverImportableSkillsAdapter(ToolAdapter):
    category = "skills"
    timeout = 15

    async def run(
        self, workspace: Any, arguments: dict[str, Any]
    ) -> ToolResult:
        skills = discover_importable_skills(workspace)
        return ToolResult(
            success=True,
            message=f"发现 {len(skills)} 个可迁移技能",
            data={"skills": skills},
        )


@register_tool(
    "migrate_skill",
    "把 discover_importable_skills 发现的某个技能复制到 AI Divine。"
    "默认复制到当前项目 .divine/skills，target 传 user 时复制到用户级"
    " ~/.divine/skills。复制前系统会请用户确认；"
    "name 必须来自发现列表，source_tool 用于区分同名技能。",
    {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "discover_importable_skills 返回的技能名",
            },
            "source_tool": {
                "type": "string",
                "description": "来源工具 claude/qoder/cursor，同名技能时必填",
            },
            "target": {
                "type": "string",
                "enum": ["project", "user"],
                "description": "project 复制到当前项目，user 复制到用户级目录",
            },
        },
        "required": ["name"],
    },
)
class MigrateSkillAdapter(ToolAdapter):
    category = "skills"
    timeout = 30

    async def run(
        self, workspace: Any, arguments: dict[str, Any]
    ) -> ToolResult:
        name = str(arguments.get("name") or "").strip()
        source_tool = str(arguments.get("source_tool") or "").strip() or None
        target = str(arguments.get("target") or "project").strip()
        if target not in {"project", "user"}:
            raise ToolExecutionError("target 只支持 project 或 user")
        try:
            result = migrate_skill(workspace, name, source_tool, target)
        except SkillMigrationError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"技能迁移失败: {exc}") from exc
        return ToolResult(
            success=True,
            message=f"技能 {result['name']} 已迁移",
            data=result,
        )
