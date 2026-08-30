from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool

# Effective per-command timeout bounds (seconds).
TERMINAL_TIMEOUT_MIN = 60
TERMINAL_TIMEOUT_MAX = 600


@register_tool(
    "terminal",
    "在本地终端执行系统命令并返回标准输出、错误输出和退出码；需要确认的命令会先征求用户同意。"
    "同一会话内工作目录会延续：上一条命令 cd 进入的目录是下一条命令的起点（显式传 cwd 可跳转）。"
    "timeout 可传 60-600 秒（默认 60），长命令（构建/测试/安装）请给足超时；"
    "输出超长时会截断保留尾部并标注。background=true 时以后台任务方式启动长驻命令"
    "（dev server、监听、长测试），立即返回 bg_id，之后用 bg_status/bg_output/bg_kill 管理。"
    "禁止用终端读取文件内容，文件读取请使用 read_file、spreadsheet、word_document 等专用工具",
    {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的终端命令",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录，默认使用当前工作区",
            },
            "timeout": {
                "type": "integer",
                "description": "前台执行时的超时秒数，60-600，默认 60",
                "default": 60,
            },
            "background": {
                "type": "boolean",
                "description": "true 时以后台任务方式启动，立即返回 bg_id，默认 false",
                "default": False,
            },
        },
        "required": ["command"],
    },
)
class TerminalAdapter(ToolAdapter):
    script_name = "terminal.py"
    category = "system"
    timeout = 60

    def effective_timeout(self, arguments: dict[str, Any]) -> int:
        """Effective timeout for the given arguments (clamped)."""
        try:
            requested = int(arguments.get("timeout") or 0)
        except (TypeError, ValueError):
            requested = 0
        return min(
            max(requested, TERMINAL_TIMEOUT_MIN),
            TERMINAL_TIMEOUT_MAX,
        )

    async def _run_background(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> ToolResult:
        from ..bg_process import bg_manager

        command = str(arguments.get("command") or "").strip()
        if not command:
            raise ToolExecutionError("命令不能为空")
        cwd_raw = str(arguments.get("cwd") or "").strip()
        cwd = Path(cwd_raw).resolve() if cwd_raw else workspace.resolve()
        if not cwd.is_dir():
            raise ToolExecutionError(f"目录不存在: {cwd}")
        session_id = str(arguments.get("session_id") or "global")
        bg = await bg_manager.start(session_id, command, str(cwd))
        if bg.status == "failed":
            raise ToolExecutionError(
                f"后台任务启动失败: {bg.error or '未知错误'}"
            )
        return ToolResult(
            success=True,
            message=f"后台任务已启动（bg_id={bg.bg_id}）",
            content=(
                f"后台任务已启动：{command}\n"
                f"bg_id={bg.bg_id}\n"
                f"cwd={cwd}\n"
                "用 bg_status 查看状态、bg_output 查看输出、bg_kill 停止任务。"
            ),
            data={
                "bg_id": bg.bg_id,
                "status": bg.status,
                "command": command,
                "cwd": str(cwd),
                "background": True,
            },
        )

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> Any:
        if arguments.get("background"):
            return await self._run_background(Path(workspace), arguments)
        # Align the inner subprocess wrapper timeout with the effective
        # per-command timeout so long builds/tests are not killed early.
        self.timeout = self.effective_timeout(arguments)
        return await super().run(
            workspace,
            arguments,
            locale=locale,
            progress_callback=progress_callback,
        )
