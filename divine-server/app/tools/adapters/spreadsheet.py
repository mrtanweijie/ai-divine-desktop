from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "spreadsheet",
    "生成带专业样式的 Excel 表格：主题配色、标题栏、斑马纹、冻结表头、自动筛选，"
    "并自动识别数字/百分比/日期/金额格式；用于项目进度、数据统计、清单等场景；"
    "本工具不能读取已有 Excel，读取请使用 read_file",
    {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "文件名"},
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录，不写入项目",
            },
            "title": {
                "type": "string",
                "description": "表格大标题，显示在首行，如“2026 年 Q3 项目进度表”；不传则不显示标题栏",
            },
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "列头",
            },
            "rows": {
                "type": "array",
                "description": (
                    "数据行；单元格可为文本、数字、布尔值、日期字符串（如 2026-08-30）、"
                    "百分比字符串（如 12.5%）；数字请直接传数字，以便排序与合计"
                ),
                "items": {"type": "array"},
            },
            "style": {
                "type": "string",
                "enum": ["ocean", "blue", "emerald", "orange", "violet", "graphite"],
                "description": (
                    "配色主题：ocean 青碧（默认）、blue 商务蓝、emerald 翡翠绿、"
                    "orange 活力橙、violet 优雅紫、graphite 极简灰；不传则按标题内容自动选择"
                ),
            },
            "total_row": {
                "type": "boolean",
                "description": "是否在末尾追加“合计”行（对数值列自动求和），默认 false",
            },
            "sheet_name": {
                "type": "string",
                "description": "工作表名称，默认“数据”",
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
            "path": str(arguments.get("path") or ""),
            "title": str(arguments.get("title") or ""),
            "style": str(arguments.get("style") or ""),
            "total_row": bool(arguments.get("total_row")),
            "sheet_name": str(arguments.get("sheet_name") or ""),
        }
