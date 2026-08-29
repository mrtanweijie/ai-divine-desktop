from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolResult, resolve_external_path
from ..registry import register_tool


@register_tool(
    "directory_tree",
    "扫描目录并返回目录树结构，用于查看文件夹层级和文件分布；自动忽略 .gitignore 与 node_modules 等目录；"
    "比 search_files 更适合了解目录结构；show_sizes=true 时附带文件大小",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要扫描的目录，默认工作区根目录",
            },
            "depth": {
                "type": "integer",
                "description": "扫描深度，默认 3，最大 6",
            },
            "show_hidden": {
                "type": "boolean",
                "description": "是否包含隐藏文件/目录",
            },
            "show_sizes": {
                "type": "boolean",
                "description": "是否附带文件大小，默认 false",
                "default": False,
            },
            "max_entries": {
                "type": "integer",
                "description": "最多返回条目数，默认 200，最大 500",
            },
        },
    },
)
class DirectoryTreeAdapter(ToolAdapter):
    script_name = "directory_tree.py"
    category = "files"
    timeout = 20
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": str(arguments.get("path") or ""),
            "depth": arguments.get("depth"),
            "show_hidden": bool(arguments.get("show_hidden")),
            "show_sizes": bool(arguments.get("show_sizes")),
            "max_entries": arguments.get("max_entries"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        params = self.build_params(arguments or {})
        # Lightweight IO: run the script's core in-process (no subprocess).
        return await self._run_in_process(
            workspace,
            params,
            "app.tools.scripts.directory_tree",
            locale=locale,
            progress_callback=progress_callback,
        )
