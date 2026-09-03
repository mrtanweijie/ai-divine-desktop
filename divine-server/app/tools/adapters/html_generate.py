from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "html_generate",
    "保存完整的 HTML 页面：分析报告、数据看板、仪表盘、落地页、简历、文档网页版等；"
    "content 传完整 HTML 源码（含 DOCTYPE 或 <html>），工具只负责校验和保存，不套用统一模板。"
    "与 ux_html 的区别：ux_html 专用于 UX 交互原型/产品界面设计稿（需用户指定风格）；"
    "本工具覆盖其余所有「要产出一个 HTML 文件」的场景。视觉规范见系统提示。",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "页面标题，可选；未提供时从 <title> 或首个 <h1> 识别",
            },
            "style": {
                "type": "string",
                "description": (
                    "视觉风格，可选：Notion/Linear/Apple/PlainText/Custom。"
                    "用户明确指定时照用；用户未指定时由你按内容性质自行选择"
                    "（数据密集用 Linear、长文报告用 Notion、展示型用 Apple），并在回复里说明选了哪个"
                ),
                "enum": ["Notion", "Linear", "Apple", "PlainText", "Custom"],
            },
            "style_note": {
                "type": "string",
                "description": "选择 Custom 时记录的个性化风格描述，其他风格可省略",
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
        "required": ["content"],
    },
)
class HtmlGenerateAdapter(ToolAdapter):
    script_name = "html_generate.py"
    category = "html"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "").strip(),
            # style 可选：留空由脚本回落默认风格，不阻断任务。
            "style": str(arguments.get("style") or "").strip(),
            "style_note": str(arguments.get("style_note") or "").strip(),
            "content": str(arguments.get("content") or ""),
            "path": str(arguments.get("path") or "html").strip(),
        }
