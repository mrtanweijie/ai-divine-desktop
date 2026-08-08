from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "spreadsheet",
    "生成 Excel 表格，用于项目进度、数据统计、清单等场景",
    {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "文件名"},
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "列头",
            },
            "rows": {
                "type": "array",
                "description": "数据行",
                "items": {"type": "array", "items": {"type": "string"}},
            },
        },
        "required": ["file_name", "headers", "rows"],
    },
)
class SpreadsheetAdapter(ToolAdapter):
    script_name = "spreadsheet.py"
    category = "spreadsheets"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_name": str(arguments.get("file_name") or "表格"),
            "headers": arguments.get("headers") or [],
            "rows": arguments.get("rows") or [],
        }
