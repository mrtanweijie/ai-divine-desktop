from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "edit_xlsx",
    "编辑已有 Excel(.xlsx) 文件：更新单元格（支持按表头文字定位列）、追加数据行"
    "（自动探测数据区末行，不覆盖已有数据）、新增工作表（带主题样式/冻结/筛选）、写公式。"
    "ops 顺序执行，任一步失败整体中止且文件不变；已实测公式与图表编辑后无损保留。"
    "修改前先用 document_outline 查看 sheet 结构。"
    "外部路径文件会生成编辑副本，不修改原文件；workspace 内文件编辑前自动备份，可用 undo_last_turn 撤销",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（.xlsx），workspace 相对路径或用户提供的绝对路径",
            },
            "ops": {
                "type": "array",
                "description": "操作序列，按顺序执行",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": [
                                "set_cells",
                                "append_rows",
                                "add_sheet",
                                "set_formula",
                                "add_chart",
                                "insert_image",
                                "delete_rows",
                                "delete_sheet",
                                "style_cells",
                            ],
                            "description": "操作类型",
                        },
                        "sheet": {
                            "type": "string",
                            "description": "工作表名；set_cells 可在 cells 条目内逐项覆盖",
                        },
                        "cells": {
                            "type": "array",
                            "description": "(set_cells) 单元格更新列表",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cell": {"type": "string", "description": "A1 坐标，如 B3"},
                                    "value": {
                                        "description": "新值；字符串/数字/布尔，公式以 = 开头"
                                    },
                                    "header": {
                                        "type": "string",
                                        "description": "列定位辅助：按表头文字解析列号（覆盖 cell 的列字母）",
                                    },
                                    "number_format": {
                                        "type": "string",
                                        "description": "可选数字格式，如 '#,##0.00'、'0.0%'",
                                    },
                                    "sheet": {"type": "string", "description": "可选，逐项覆盖工作表"},
                                },
                                "required": ["cell", "value"],
                            },
                        },
                        "rows": {
                            "type": "array",
                            "description": "(append_rows/add_sheet) 数据行，每行为值数组",
                        },
                        "name": {"type": "string", "description": "(add_sheet/delete_sheet) 工作表名"},
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "(add_sheet) 表头行，套用生成器主题样式",
                        },
                        "theme": {
                            "type": "string",
                            "description": "(add_sheet) 配色主题，默认 blue（ocean/blue/emerald/orange/violet/graphite）",
                        },
                        "cell": {"type": "string", "description": "(set_formula) 公式目标单元格"},
                        "formula": {
                            "type": "string",
                            "description": "(set_formula) 公式，如 'SUM(B2:B13)' 或 '=SUM(B2:B13)'",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["bar", "column", "line", "area", "pie", "doughnut", "scatter"],
                            "description": "(add_chart) 图表类型",
                        },
                        "title": {"type": "string", "description": "(add_chart) 图表标题"},
                        "anchor": {
                            "type": "string",
                            "description": "(add_chart/insert_image) 左上角锚点单元格，如 E2",
                        },
                        "categories_ref": {
                            "type": "string",
                            "description": "(add_chart) 分类轴数据范围，如 'A2:A13'（单列）",
                        },
                        "series": {
                            "type": "array",
                            "description": "(add_chart) 数据系列，每项单列范围",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "系列名"},
                                    "ref": {"type": "string", "description": "数据范围，如 'B1:B13'（单列）"},
                                },
                                "required": ["ref"],
                            },
                        },
                        "image_path": {
                            "type": "string",
                            "description": "(insert_image) 图片路径（png/jpg），嵌入后不依赖原文件",
                        },
                        "start": {
                            "type": "integer",
                            "description": "(delete_rows) 起始行号（1 基）",
                        },
                        "count": {
                            "type": "integer",
                            "description": "(delete_rows) 删除行数，默认 1",
                        },
                        "range": {
                            "type": "string",
                            "description": "(style_cells) 目标范围，如 'A1:C10' 或单格 'B2'（整列写法会拒绝，请给明确行范围）",
                        },
                        "bold": {"type": "boolean", "description": "(style_cells) 加粗"},
                        "italic": {"type": "boolean", "description": "(style_cells) 斜体"},
                        "underline": {"type": "boolean", "description": "(style_cells) 下划线"},
                        "font_size": {"type": "number", "description": "(style_cells) 字号"},
                        "font_color": {"type": "string", "description": "(style_cells) 字体颜色，十六进制如 'FF0000'"},
                        "fill_color": {"type": "string", "description": "(style_cells) 填充色，十六进制如 'FFFF00'"},
                        "align": {
                            "type": "string",
                            "enum": ["left", "center", "right"],
                            "description": "(style_cells) 水平对齐",
                        },
                        "number_format": {
                            "type": "string",
                            "description": "(style_cells) 数字格式，如 '#,##0.00'",
                        },
                        "width": {"type": "number", "description": "(insert_image) 可选，像素宽"},
                        "height": {"type": "number", "description": "(insert_image) 可选，像素高"},
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["path", "ops"],
    },
)
class EditXlsxAdapter(ToolAdapter):
    script_name = "edit_xlsx.py"
    category = "documents"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": str(arguments.get("path") or ""),
            "ops": arguments.get("ops") or [],
            "session_id": str(arguments.get("session_id") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
