from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "presentation",
    "生成 PPT 幻灯片演示文稿，用于汇报、培训、产品介绍等场景",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "演示文稿标题"},
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录，不写入项目",
            },
            "slides": {
                "type": "array",
                "description": "幻灯片列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string", "description": "幻灯片标题"},
                        "body": {
                            "type": "string",
                            "description": "正文内容，可用换行分隔多个要点",
                        },
                    },
                    "required": ["heading", "body"],
                },
            },
        },
        "required": ["title", "slides"],
    },
)
class PresentationAdapter(ToolAdapter):
    script_name = "presentation.py"
    category = "presentations"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "未命名演示文稿"),
            "slides": arguments.get("slides") or [],
            "path": str(arguments.get("path") or ""),
        }
