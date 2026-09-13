from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pdf_render",
    "把 Markdown 正文渲染为排版美观的 PDF；生成 PDF 报告时先产出完整 Markdown 再调用本工具。"
    "content 传 Markdown 正文，或用 file_path 指向已有 Markdown 文件；"
    "style/theme/color_scheme 可选；默认保存到应用输出目录 pdf，指定项目内目录时传 path。",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "PDF 标题；默认取 Markdown 首个标题"},
            "content": {
                "type": "string",
                "description": "Markdown 正文；若开头是整页 HTML 封面（width/height 100% + page-break-after），工具会自动识别为封面页；不要包含下载链接或文件路径说明",
            },
            "file_path": {
                "type": "string",
                "description": "可选，已存在的 Markdown 文件路径；与 content 二选一",
            },
            "style": {
                "type": "string",
                "enum": ["modern", "academic", "corporate", "minimal", "playful"],
                "description": "排版风格",
            },
            "theme": {
                "type": "string",
                "enum": ["universal", "resume", "modern", "academic", "travel", "roadmap", "minimal", "notion", "linear", "apple"],
                "description": (
                    "主题 ID，优先于 style。"
                    "本工具只渲染 Markdown，因此不含页式模板主题；"
                    "论文/报告四套（academic_report/thesis_paper/data_report/research_report）"
                    "是页结构固定的模板，请改用 pdf_generate 并传对应 kind"
                ),
            },
            "color_scheme": {
                "type": "string",
                "enum": [
                    "teal", "blue", "green", "warm", "monochrome", "purple",
                    "iceblue", "desert", "vintage", "midnight", "pureblack",
                    "mistsage", "mistblue", "duskmauve", "lotuspink",
                    "dunesand", "smokegray",
                ],
                "description": "配色方案（经典/旅行杂志预设）；不传时自动选择",
            },
            "theme_colors": {
                "type": "object",
                "description": (
                    "可选，自定义主题色变量（对所有主题生效）："
                    "旅行主题用 --color-primary/--color-accent/--bg-cover/--bg-highlight，"
                    "其他主题用 --primary/--accent，只传主色即可自动派生整套配色"
                ),
            },
            "paper_size": {
                "type": "string",
                "enum": ["A4", "Letter", "Legal"],
                "description": "纸张大小，默认 A4",
            },
            "cover": {
                "type": "boolean",
                "description": "是否生成封面页，默认 false；travel 主题固定生成封面",
            },
            "toc": {
                "type": "boolean",
                "description": "是否生成目录，默认 false",
            },
            "file_name": {
                "type": "string",
                "description": "可选，PDF 文件名；默认由 title 生成",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 pdf",
            },
        },
    },
)
class PdfRenderAdapter(ToolAdapter):
    script_name = "pdf_render.py"
    category = "pdf"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "").strip(),
            "content": str(arguments.get("content") or ""),
            "file_path": str(arguments.get("file_path") or "").strip(),
            "style": str(arguments.get("style") or "modern").strip(),
            "theme": str(arguments.get("theme") or "").strip(),
            "color_scheme": str(arguments.get("color_scheme") or "blue").strip(),
            "theme_colors": arguments.get("theme_colors") or {},
            "paper_size": str(arguments.get("paper_size") or "A4").strip(),
            "cover": bool(arguments.get("cover")),
            "toc": bool(arguments.get("toc")),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(
            workspace, arguments.get("file_path")
        )
        return [external] if external else []
