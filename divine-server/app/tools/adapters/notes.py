from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "notes",
    "生成 Markdown 笔记文件，用于会议记录、知识整理、待办清单等场景",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "笔记标题"},
            "content": {"type": "string", "description": "Markdown 正文"},
        },
        "required": ["title", "content"],
    },
)
class NotesAdapter(ToolAdapter):
    script_name = "notes.py"
    category = "notes"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "未命名笔记"),
            "content": str(arguments.get("content") or ""),
        }
