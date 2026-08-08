from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "rag_index",
    "扫描工作区文本文件并建立本地向量索引，用于后续 rag_search 检索；索引会保存在本地数据库",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要索引的目录，默认整个工作区",
            }
        },
    },
)
class RagIndexAdapter(ToolAdapter):
    script_name = "rag_index.py"
    category = "files"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"path": str(arguments.get("path") or "")}

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
