from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "word_document",
    "生成一份 Word 文档，用于周报、合同、会议纪要等场景；"
    "theme 可选 universal/notion/linear/apple/modern/academic/travel/roadmap/minimal，"
    "用于控制字体、标题色、行距和页边距",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "文档标题"},
            "theme": {
                "type": "string",
                "enum": [
                    "universal",
                    "notion",
                    "linear",
                    "apple",
                    "modern",
                    "academic",
                    "travel",
                    "roadmap",
                    "minimal",
                ],
                "description": "文档风格，默认 universal",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录，不写入项目",
            },
            "sections": {
                "type": "array",
                "description": "文档章节",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
        },
        "required": ["title", "sections"],
    },
)
class WordDocumentAdapter(ToolAdapter):
    script_name = "word_document.py"
    category = "documents"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "未命名文档"),
            "theme": str(arguments.get("theme") or arguments.get("style") or "universal").strip(),
            "sections": arguments.get("sections") or [],
            "path": str(arguments.get("path") or ""),
        }
