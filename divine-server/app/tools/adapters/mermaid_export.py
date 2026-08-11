from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "mermaid_export",
    "把 Mermaid 流程图/时序图/架构图源码保存为 .mmd 文件；用户要求导出或保存流程图时使用，content 传 Mermaid 源码（不要带围栏代码块），path 可指定 workspace 内相对目录，默认保存到 diagrams",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "图标题，用于生成文件名"},
            "content": {
                "type": "string",
                "description": "Mermaid 源码，不要包含 ```mermaid 围栏代码块",
            },
            "file_name": {
                "type": "string",
                "description": "可选，指定文件名；默认由 title 生成",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认 diagrams",
            },
        },
        "required": ["content"],
    },
)
class MermaidExportAdapter(ToolAdapter):
    script_name = "mermaid_export.py"
    category = "diagrams"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "流程图").strip(),
            "content": str(arguments.get("content") or "").strip(),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }
