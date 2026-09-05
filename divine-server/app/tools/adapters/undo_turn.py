from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..checkpoint import restore_latest
from ..office_backup import restore_latest_batch
from ..registry import register_tool


@register_tool(
    "undo_last_turn",
    "撤销 agent 最近的文件改动：把项目工作区恢复到改动前的快照"
    "（包括删除 agent 新建的文件，git 仓库的 .git 不受影响）。"
    "Office 编辑（fill_template/edit_docx）的文件通过编辑备份恢复。"
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
        # Office 编辑的撤销走字节级备份（checkpoint 快照单文件上限 512KB，
        # 覆盖不了带图 docx/xlsx，见 docs/design/017-office-edit-closed-loop-20260906.md §5.3）。
        office = restore_latest_batch(session_id)
        office_restored: list[dict] = office.get("restored") or []
        if (
            not summary.get("restored")
            and not summary.get("deleted")
            and not office_restored
        ):
            return ToolResult(
                success=True,
                message="没有可撤销的改动",
                content=(
                    "没有找到可撤销的文件改动（可能没有快照，或工作区与最近"
                    "一次快照状态一致）。如需回退 git 已跟踪文件请用 git_revert。"
                ),
                data=summary,
            )
        parts: list[str] = []
        if summary.get("restored") or summary.get("deleted"):
            parts.append(
                f"恢复 {summary.get('restored', 0)} 个文件，"
                f"删除 {summary.get('deleted', 0)} 个新建文件"
            )
        if office_restored:
            names = "、".join(
                Path(item["original"]).name for item in office_restored
            )
            parts.append(f"从编辑备份还原 {names}")
        message = f"已撤销最近一轮改动：{'；'.join(parts)}"
        return ToolResult(
            success=True,
            message=message,
            content=(
                f"{message}。"
                "撤销前的状态已自动存档，用户反悔时可再次调用本工具找回。"
                "请向用户简要说明恢复了什么，不要重复执行刚被撤销的修改。"
            ),
            data={**summary, "office_restored": office_restored},
        )
