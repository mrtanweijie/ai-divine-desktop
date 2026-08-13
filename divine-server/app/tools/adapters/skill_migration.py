from __future__ import annotations

from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ...skills import (
    SkillMigrationError,
    discover_importable_skills,
    migrate_skill,
    migrate_skills,
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
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        skills = discover_importable_skills(workspace)
        return ToolResult(
            success=True,
            message=f"发现 {len(skills)} 个可迁移技能",
            data={"skills": skills},
            message_key="tool.skillsDiscovered",
            message_params={"count": len(skills)},
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
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
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
            message_key="tool.skillMigrated",
            message_params={"name": result["name"]},
        )


@register_tool(
    "migrate_skills",
    "批量迁移 discover_importable_skills 发现的多个技能到 AI Divine。"
    "一次确认后逐个复制，已存在的技能会自动跳过。"
    "用户要求迁移多个或全部技能时优先使用本工具，不要逐个调用 migrate_skill。",
    {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要迁移的技能名列表，来自 discover_importable_skills",
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
        "required": ["names"],
    },
)
class MigrateSkillsAdapter(ToolAdapter):
    category = "skills"
    timeout = 60

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        names = [
            str(item or "").strip()
            for item in (arguments.get("names") or [])
            if str(item or "").strip()
        ]
        if not names:
            raise ToolExecutionError("names 不能为空")
        source_tool = str(arguments.get("source_tool") or "").strip() or None
        target = str(arguments.get("target") or "project").strip()
        if target not in {"project", "user"}:
            raise ToolExecutionError("target 只支持 project 或 user")
        try:
            result = migrate_skills(
                workspace, names, source_tool, target
            )
        except SkillMigrationError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"技能批量迁移失败: {exc}") from exc
        migrated = len(result.get("migrated") or [])
        skipped = len(result.get("skipped") or [])
        failed = len(result.get("failed") or [])
        return ToolResult(
            success=bool(result.get("ok")) and failed == 0,
            message=(
                f"已迁移 {migrated} 个，跳过 {skipped} 个，"
                f"失败 {failed} 个"
            ),
            data=result,
            message_key="tool.skillsMigrated",
            message_params={
                "migrated": migrated,
                "skipped": skipped,
                "failed": failed,
            },
        )
