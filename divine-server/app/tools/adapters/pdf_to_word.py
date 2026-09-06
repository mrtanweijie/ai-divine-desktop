from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pdf_to_word",
    "把 PDF 的文本内容转换为可编辑的 Word(.docx)：标题/表格/列表保留，"
    "输出到 workspace 的 documents 目录。适合'这份 PDF 我想改改'的场景"
    "（转换后用 edit_docx 继续编辑）。"
    "保真度说明：复杂排版（多栏/艺术字）可能存在差异；"
    "扫描件/纯图片 PDF 无文本层，无法转换（OCR 不在支持范围）。原 PDF 只读不动",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "PDF 文件路径（workspace 相对路径或用户提供的绝对路径）",
            },
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
                "description": "输出 Word 的风格，默认 universal",
            },
            "title": {
                "type": "string",
                "description": "输出文件名（不含 .docx），默认用 PDF 文件名",
            },
        },
        "required": ["path"],
    },
)
class PdfToWordAdapter(ToolAdapter):
    script_name = "pdf_to_word.py"
    category = "documents"
    timeout = 120  # 大 PDF 的文本提取与 docx 渲染耗时更长
    allow_external_paths = True  # 可读取用户提供的任意路径 PDF（只读输入）

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": str(arguments.get("path") or ""),
            "theme": str(arguments.get("theme") or arguments.get("style") or "universal").strip(),
            "title": str(arguments.get("title") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
