from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "html_common",
    "按用户要求原样保存完整 HTML 页面：不注入设计 token 基座、不做简历拦截，"
    "内容一字不改直接落盘。适用：用户提供了自己的 HTML 模板（如自带简历模板）、"
    "用户明确要求自定义版式/原样输出、需要保存外部 HTML 内容。"
    "注意：简历的默认路径仍是模板管线（PDF 用 pdf_generate、可编辑 HTML 用 html_resume），"
    "仅当用户明确提供内容或明确要求自定义时才用本工具。"
    "与 html_generate 的区别：html_generate 会注入风格 token 基座并做静态校验，"
    "适合生成通用页面；本工具零加工。",
    {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "完整 HTML 页面源码，必须包含 DOCTYPE 或 <html>，原样保存",
            },
            "title": {
                "type": "string",
                "description": "页面标题（用于文件命名），可选；未提供时从 <title> 或首个 <h1> 识别",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 html 类别",
            },
        },
        "required": ["content"],
    },
)
class HtmlCommonAdapter(ToolAdapter):
    script_name = "html_common.py"
    category = "html"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": str(arguments.get("content") or ""),
            "title": str(arguments.get("title") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }
