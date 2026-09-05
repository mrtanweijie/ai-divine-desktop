from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "fill_template",
    "填充 Word(.docx) 模板中的 {{占位符}}，用于合同、offer、通知函、介绍信等套模板场景。"
    "values 为占位符→值映射（键不带花括号）；list_values 支持表格整行展开"
    "（值为对象数组，模板行内用 {{key.字段名}} 引用记录字段）。"
    "外部路径文件会生成编辑副本，不修改原文件；workspace 内文件编辑前自动备份，可用 undo_last_turn 撤销。"
    "填充前可先用 read_file 查看模板内容确认占位符名称",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "模板文件路径（.docx），workspace 相对路径或用户提供的绝对路径",
            },
            "values": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": '占位符→值映射，如 {"company": "某某科技", "sign_date": "2026年9月6日"}',
            },
            "list_values": {
                "type": "object",
                "description": (
                    "表格行填充：键为占位符名，值为对象数组，逐行展开整行；"
                    '模板行单元格内用 {{key.字段}} 引用，如 {"items": [{"name": "..", "qty": "2"}]}'
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
        "required": ["path", "values"],
    },
)
class FillTemplateAdapter(ToolAdapter):
    script_name = "fill_template.py"
    category = "documents"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        list_values = arguments.get("list_values")
        return {
            "path": str(arguments.get("path") or ""),
            "values": arguments.get("values") or {},
            "list_values": list_values if isinstance(list_values, dict) else {},
            "session_id": str(arguments.get("session_id") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
