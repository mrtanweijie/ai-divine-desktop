from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "draw_svg",
    "从零生成 SVG 矢量图/图标/插画；用户要求画 SVG 时使用，content 必须是完整合法 SVG 源码（以 <svg 开头）。"
    "生成时给关键元素加简短唯一的 id（如 eye-left、hair、body），便于后续 edit_svg 局部修改。"
    "不要在正文输出解释，直接把完整 SVG 代码传给 content。",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "SVG 标题，用于生成文件名；可选",
            },
            "file_name": {
                "type": "string",
                "description": "可选，指定文件名；默认由 title 生成",
            },
            "content": {
                "type": "string",
                "description": "完整 SVG 源码，不要包含 ```svg 围栏代码块",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认 svg",
            },
        },
        "required": ["content"],
    },
)
class DrawSvgAdapter(ToolAdapter):
    script_name = "draw_svg.py"
    category = "svg"
    timeout = 20

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "").strip(),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "content": str(arguments.get("content") or ""),
            "path": str(arguments.get("path") or "").strip(),
        }
