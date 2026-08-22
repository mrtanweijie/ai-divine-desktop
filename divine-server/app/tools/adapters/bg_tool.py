from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool

_BG_TOOLS = {"bg_status", "bg_output", "bg_kill"}


def _session_id(arguments: dict[str, Any]) -> str | None:
    raw = arguments.get("session_id")
    return str(raw) if raw else None


@register_tool(
    "bg_status",
    "查看本会话的后台任务列表（不传 bg_id）或单个后台任务状态（传 bg_id）："
    "返回状态（running/exited/killed）、退出码、运行时长。",
    {
        "type": "object",
        "properties": {
            "bg_id": {
                "type": "string",
                "description": "可选；不传时列出本会话所有后台任务",
            }
        },
    },
)
class BgStatusAdapter(ToolAdapter):
    category = "system"
    timeout = 10

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        from ..bg_process import bg_manager

        session_id = _session_id(arguments)
        bg_id = str(arguments.get("bg_id") or "").strip()
        if bg_id:
            bg = bg_manager.get(bg_id, session_id)
            if bg is None:
                raise ToolExecutionError(f"后台任务不存在: {bg_id}")
            summary = bg.summary()
            return ToolResult(
                success=True,
                message=f"bg {bg_id}：{summary['status']}",
                content=json.dumps(summary, ensure_ascii=False),
                data=summary,
            )
        processes = bg_manager.list_for_session(session_id or "")
        summaries = [proc.summary() for proc in processes]
        return ToolResult(
            success=True,
            message=f"本会话后台任务：{len(summaries)} 个",
            content=json.dumps(summaries, ensure_ascii=False),
            data={"count": len(summaries), "processes": summaries},
        )


@register_tool(
    "bg_output",
    "读取后台任务最近输出（stdout/stderr 合并，保留尾部最多 16KB），用于查看 dev server 日志或长任务进度。",
    {
        "type": "object",
        "properties": {
            "bg_id": {
                "type": "string",
                "description": "后台任务 id（terminal background=true 启动时返回）",
            }
        },
        "required": ["bg_id"],
    },
)
class BgOutputAdapter(ToolAdapter):
    category = "system"
    timeout = 10

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        from ..bg_process import bg_manager

        session_id = _session_id(arguments)
        bg_id = str(arguments.get("bg_id") or "").strip()
        if not bg_id:
            raise ToolExecutionError("bg_id 不能为空")
        bg = bg_manager.get(bg_id, session_id)
        if bg is None:
            raise ToolExecutionError(f"后台任务不存在: {bg_id}")
        output, truncated, total = bg.tail_output()
        if not output:
            output = f"（暂无输出，状态: {bg.status}）"
        return ToolResult(
            success=True,
            message=f"bg {bg_id} 输出（共 {total} 字节）",
            content=output,
            data={
                "bg_id": bg_id,
                "status": bg.status,
                "exit_code": bg.exit_code,
                "truncated": truncated,
                "bytes": total,
            },
        )


@register_tool(
    "bg_kill",
    "停止后台任务（terminate，5 秒后强制 kill）。停止 dev server 或不再需要的长任务时使用；"
    "执行前需要用户确认。",
    {
        "type": "object",
        "properties": {
            "bg_id": {
                "type": "string",
                "description": "后台任务 id",
            }
        },
        "required": ["bg_id"],
    },
)
class BgKillAdapter(ToolAdapter):
    category = "system"
    timeout = 15

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        from ..bg_process import bg_manager

        session_id = _session_id(arguments)
        bg_id = str(arguments.get("bg_id") or "").strip()
        if not bg_id:
            raise ToolExecutionError("bg_id 不能为空")
        bg = await bg_manager.kill(bg_id, session_id)
        if bg is None:
            raise ToolExecutionError(f"后台任务不存在: {bg_id}")
        return ToolResult(
            success=True,
            message=f"后台任务已停止: {bg_id}",
            content=f"后台任务 {bg_id} 已停止（{bg.command}）",
            data={"bg_id": bg_id, "status": bg.status},
        )


def is_bg_tool(name: str) -> bool:
    return name in _BG_TOOLS


__all__ = ["BgStatusAdapter", "BgOutputAdapter", "BgKillAdapter", "is_bg_tool"]
