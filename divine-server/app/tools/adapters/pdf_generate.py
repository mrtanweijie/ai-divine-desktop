from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "pdf_generate",
    "统一 PDF 生成入口：根据用户需求自动选择 Report/Travel/Roadmap/Book/Slide 配方，"
    "解析结构、生成正文并渲染为美观 PDF。"
    "生成个人简历时，Agent 应根据用户信息整理 resume_data 结构化 JSON 后传入；"
    "prompt 传用户需求；kind 可选 report/travel/roadmap/book/slide；"
    "style 支持 modern/academic/corporate/minimal/playful，"
    "color_scheme 支持 blue/green/warm/monochrome/purple；"
    "默认保存到应用输出目录 pdf，用户指定项目内目录时传 path。",
    {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "用户对 PDF 文档的需求描述"},
            "markdown": {
                "type": "string",
                "description": (
                    "可选，完整 Markdown 正文；传入后直接按该内容渲染 PDF，"
                    "可使用 ![图表标题](图表文件路径) 嵌入之前生成的图表"
                ),
            },
            "kind": {
                "type": "string",
                "enum": ["report", "travel", "roadmap", "book", "slide", "resume"],
                "description": "文档配方；不传时自动识别",
            },
            "style": {
                "type": "string",
                "enum": ["modern", "academic", "corporate", "minimal", "playful"],
                "description": "排版风格",
            },
            "theme": {
                "type": "string",
                "enum": ["universal", "resume", "professional", "creative", "minimal", "boss_zhipin", "finance", "linkedin", "kami", "kami_white", "modern", "academic", "travel", "roadmap", "notion", "linear", "apple"],
                "description": "主题 ID，优先于 style；report 默认 modern，travel 默认 travel，roadmap 默认 roadmap",
            },
            "color_scheme": {
                "type": "string",
                "enum": ["blue", "green", "warm", "monochrome", "purple"],
                "description": "配色方案",
            },
            "paper_size": {
                "type": "string",
                "enum": ["A4", "Letter", "Legal"],
                "description": "纸张大小，默认 A4",
            },
            "cover": {
                "type": "boolean",
                "description": "是否生成封面页，默认 false",
            },
            "toc": {
                "type": "boolean",
                "description": "是否生成目录，默认 false",
            },
            "file_name": {
                "type": "string",
                "description": "可选，PDF 文件名；默认由 prompt 生成",
            },
            "resume_data": {
                "type": "object",
                "description": "简历结构化数据，推荐一页简历结构：name/target/contact/summary/core_skills/work/projects/education；kind=resume 时优先使用此数据渲染，不再走 LLM 生成",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 pdf",
            },
        },
        "required": ["prompt"],
    },
)
class PdfGenerateAdapter(ToolAdapter):
    script_name = "pdf_generate.py"
    category = "pdf"
    timeout = 300

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "prompt": str(arguments.get("prompt") or "").strip(),
            "kind": str(arguments.get("kind") or "").strip(),
            "style": str(arguments.get("style") or "").strip(),
            "theme": str(arguments.get("theme") or "").strip(),
            "color_scheme": str(arguments.get("color_scheme") or "").strip(),
            "paper_size": str(arguments.get("paper_size") or "A4").strip(),
            "cover": bool(arguments.get("cover")),
            "toc": bool(arguments.get("toc")),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "resume_data": arguments.get("resume_data") or {},
            "path": str(arguments.get("path") or "").strip(),
            "markdown": str(arguments.get("markdown") or "").strip(),
        }
