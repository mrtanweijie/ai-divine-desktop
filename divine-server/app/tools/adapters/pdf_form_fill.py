from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pdf_form_fill",
    "按字段名填写 PDF 交互表单（AcroForm）：文本字段直接赋值，"
    "复选框/单选用 true/false 语义，下拉的值必须在选项内（先用 pdf_form_fields 查看字段清单）。"
    "未命中的字段名会整体中止且文件不变。"
    "外部路径文件会生成编辑副本，不修改原文件；workspace 内文件填写前自动备份，可用 undo_last_turn 撤销；"
    "flatten=true 可把值烧进页面（之后不可再编辑，默认保留可编辑）",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "PDF 文件路径（workspace 相对路径或用户提供的绝对路径）",
            },
            "values": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": '字段名→值映射，如 {"company": "某某科技", "agree": "true"}；'
                "复选框用 true/false，下拉的值需在选项内",
            },
            "flatten": {
                "type": "boolean",
                "description": "是否把表单值烧进页面文本（默认 false，保留可编辑字段）",
            },
        },
        "required": ["path", "values"],
    },
)
class PdfFormFillAdapter(ToolAdapter):
    script_name = "pdf_form_fill.py"
    category = "documents"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": str(arguments.get("path") or ""),
            "values": arguments.get("values") or {},
            "flatten": bool(arguments.get("flatten")),
            "session_id": str(arguments.get("session_id") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
