"""MCP 工具的轻量 adapter：满足 _execute_tool 的鸭子类型契约。

不注册进静态 registry——工具列表由 ``_build_tools`` 按 manager 快照动态
构建，但执行/审批/持久化复用同一条管线（_handle_adapter_call）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..tools.base import ToolExecutionError, ToolResult
from .manager import McpToolInfo, mcp_manager


class McpToolAdapter:
    """Duck-typed adapter (timeout/external_paths/run) for one MCP tool."""

    category = "mcp"
    timeout = 200  # 覆盖 manager 的单次调用超时 + 连接余量
    supports_progress = False
    allow_external_paths = False

    def __init__(self, info: McpToolInfo) -> None:
        self.info = info
        self.name = info.key

    def external_paths(self, workspace: Path, arguments: dict[str, Any]) -> list[str]:
        return []

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        try:
            text = await mcp_manager.call(self.info.key, arguments or {})
        except RuntimeError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — 统一转成模型可读的错误
            raise ToolExecutionError(
                f"MCP 工具执行失败: {type(exc).__name__}: {str(exc)[:300]}"
            ) from exc
        return ToolResult(
            success=True,
            message=(
                f"MCP {self.info.server_name}.{self.info.tool_name} 执行完成"
            ),
            content=text,
            data={
                "server": self.info.server_id,
                "tool": self.info.tool_name,
            },
        )
