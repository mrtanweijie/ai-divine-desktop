from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "ux_html",
    "保存 Agent 根据需求文档设计好的完整 UX 交互 HTML 页面；"
    "当用户要求把需求文档/PRD 实现成交互式产品界面、UX 原型、可点击演示页面时，"
    "先分析文档并自行设计贴合产品形态的 HTML/CSS/JS，再调用本工具写入文件；"
    "content 必须传完整 HTML 源码（包含 DOCTYPE 或 <html>），工具只负责校验和保存，不套用统一模板。"
    "页面视觉必须参考 Apple / Linear / Notion：留白充足、不使用渐变和重阴影、"
    "正文 #111827、辅助 #6B7280、圆角 10px、间距使用 16 的倍数，主色按风格定义。"
    "style 必须由用户在 Notion/Linear/Apple/PlainText/Custom 中明确选择后才能调用。",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "页面标题，可选；未提供时从 <title> 或首个 <h1> 识别",
            },
            "style": {
                "type": "string",
                "description": "用户明确选择的交互风格，只能是 Notion/Linear/Apple/PlainText/Custom",
                "enum": ["Notion", "Linear", "Apple", "PlainText", "Custom"],
            },
            "style_note": {
                "type": "string",
                "description": "用户选择 Custom 时记录的个性化风格描述，其他风格可省略",
            },
            "content": {
                "type": "string",
                "description": "完整 HTML 页面源码，必须包含 DOCTYPE 或 <html>，用于直接保存为 .html 文件",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 html 类别",
            },
        },
        "required": ["style", "content"],
    },
)
class UxHtmlAdapter(ToolAdapter):
    script_name = "ux_html.py"
    category = "html"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "").strip(),
            "style": str(arguments.get("style") or "").strip(),
            "style_note": str(arguments.get("style_note") or "").strip(),
            "content": str(arguments.get("content") or ""),
            "path": str(arguments.get("path") or "html").strip(),
        }
