from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "ux_html",
    "保存 Agent 设计好的完整 UX 交互 HTML 页面；content 传完整 HTML 源码（含 DOCTYPE 或 <html>），"
    "工具只负责校验和保存，不套用统一模板；视觉规范见系统提示（Apple/Linear/Notion 风格）。"
    "style 必须为用户明确选择的 Notion/Linear/Apple/PlainText/Obsidian/Custom 之一。",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "页面标题，可选；未提供时从 <title> 或首个 <h1> 识别",
            },
            "style": {
                "type": "string",
                "description": "用户明确选择的交互风格，只能是 Notion/Linear/Apple/PlainText/Obsidian/Custom",
                "enum": ["Notion", "Linear", "Apple", "PlainText", "Obsidian", "Custom"],
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
            "canvas": {
                "type": "string",
                "description": (
                    "画布类型：desktop（默认，桌面 Web 页面）/ mobile（手机 App 原型）。"
                    "需求为 iOS/Android/手机 App 时必传 mobile，静态校验按移动端规则执行"
                ),
                "enum": ["desktop", "mobile"],
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
            "canvas": str(arguments.get("canvas") or "desktop").strip().lower(),
        }
