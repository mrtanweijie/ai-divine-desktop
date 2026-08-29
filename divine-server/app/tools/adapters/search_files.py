from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolResult
from ..registry import register_tool


@register_tool(
    "search_files",
    "搜索工作区中的文件，按文件名或相对路径关键字过滤，返回匹配文件的相对路径和大小；需要查看文件内容时再调用 read_file",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "文件名或路径包含的关键字，可省略",
            },
            "path": {
                "type": "string",
                "description": "workspace 内要搜索的相对目录，默认搜索整个工作区",
            },
        },
    },
)
class SearchFilesAdapter(ToolAdapter):
    script_name = "search_files.py"
    category = "files"
    timeout = 20

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": str(arguments.get("query") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }

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
            "app.tools.scripts.search_files",
            locale=locale,
            progress_callback=progress_callback,
        )
