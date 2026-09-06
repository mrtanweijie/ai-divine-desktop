from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pdf_form_fields",
    "读取 PDF 的交互表单（AcroForm）字段清单：字段名/类型/当前值/可选状态/所在页。"
    "在 pdf_form_fill 填写前必须先调用本工具获取字段名。"
    "字段清单为空说明该 PDF 没有交互表单（如扫描件），无法程序化填写",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "PDF 文件路径（workspace 相对路径或用户提供的绝对路径）",
            },
        },
        "required": ["path"],
    },
)
class PdfFormFieldsAdapter(ToolAdapter):
    script_name = "pdf_form_fields.py"
    category = "documents"
    timeout = 30
    allow_external_paths = True

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
