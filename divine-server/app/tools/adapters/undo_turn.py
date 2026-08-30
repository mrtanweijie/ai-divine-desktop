from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..checkpoint import restore_latest
from ..registry import register_tool


@register_tool(
    "undo_last_turn",
    "撤销 agent 最近的文件改动：把项目工作区恢复到改动前的快照"
    "（包括删除 agent 新建的文件，git 仓库的 .git 不受影响）。"
    "仅当用户明确要求撤销/回滚/恢复刚才的改动时调用；"
    "恢复前当前状态会先存档，用户反悔可再次调用本工具找回。"
    "没有可撤销的改动时返回提示。git 已跟踪文件的版本回退请用 git_revert。",
    {"type": "object", "properties": {}},
)
class UndoLastTurnAdapter(ToolAdapter):
    category = "system"
    timeout = 60

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        session_id = str(arguments.get("session_id") or "").strip()
        if not session_id:
            raise ToolExecutionError("缺少会话标识，无法定位快照")
        summary = restore_latest(Path(workspace).resolve(), session_id)
        if not summary.get("restored") and not summary.get("deleted"):
            return ToolResult(
                success=True,
                message="没有可撤销的改动",
                content=(
                    "没有找到可撤销的文件改动（可能没有快照，或工作区与最近"
                    "一次快照状态一致）。如需回退 git 已跟踪文件请用 git_revert。"
                ),
                data=summary,
            )
        message = (
            f"已撤销最近一轮改动：恢复 {summary.get('restored', 0)} 个文件，"
            f"删除 {summary.get('deleted', 0)} 个新建文件"
        )
        return ToolResult(
            success=True,
            message=message,
            content=(
                f"{message}。"
                "撤销前的状态已自动存档，用户反悔时可再次调用本工具找回。"
                "请向用户简要说明恢复了什么，不要重复执行刚被撤销的修改。"
            ),
            data=summary,
        )
