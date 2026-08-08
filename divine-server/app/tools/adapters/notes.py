from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "notes",
    "生成 Markdown 笔记文件，用于会议记录、知识整理、待办清单等场景；title 未提供时会从正文首行或首个标题自动命名",
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
        title = str(arguments.get("title") or "").strip()
        content = str(arguments.get("content") or "")
        if not title:
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    stripped = stripped.lstrip("#").strip()
                if stripped:
                    title = stripped[:60]
                    break
        return {
            "title": title or "未命名笔记",
            "content": content,
        }
