from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "edit_docx",
    "编辑已有 Word(.docx) 文档：替换文字（run 级保样式）、整段替换、"
    "更新表格单元格（按表头+行首列值定位）、文末追加章节、删除段落。"
    "ops 顺序执行，任一步定位失败整体中止且文件不变。"
    "修改前先用 document_outline 查看结构定位目标。"
    "外部路径文件会生成编辑副本，不修改原文件；workspace 内文件编辑前自动备份，可用 undo_last_turn 撤销",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文档路径（.docx），workspace 相对路径或用户提供的绝对路径",
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
                                "replace_text",
                                "set_paragraph",
                                "set_table_cell",
                                "append_section",
                                "delete_paragraph",
                            ],
                            "description": "操作类型",
                        },
                        "find": {
                            "type": "string",
                            "description": "(replace_text) 要查找的文本，需完整落在同一段落内",
                        },
                        "replace": {
                            "type": "string",
                            "description": "(replace_text) 替换文本",
                        },
                        "all": {
                            "type": "boolean",
                            "description": "(replace_text) 替换全部命中，默认只替换第一处",
                        },
                        "regex": {
                            "type": "boolean",
                            "description": "(replace_text) find 是否为正则表达式，默认 false",
                        },
                        "match": {
                            "type": "string",
                            "description": "(set_paragraph/delete_paragraph/replace_text) 段落定位文本（段落内包含即命中）",
                        },
                        "text": {
                            "type": "string",
                            "description": "(set_paragraph/set_table_cell) 新文本",
                        },
                        "table": {
                            "type": "integer",
                            "description": "(set_table_cell) 表格序号（1 开始，document_outline 输出的表格清单序号）",
                        },
                        "header": {
                            "type": "string",
                            "description": "(set_table_cell) 列定位：目标列的表头文字（与 col 二选一，优先）",
                        },
                        "row_key": {
                            "type": "string",
                            "description": "(set_table_cell) 行定位：该行第一列的值（与 row 二选一，优先）",
                        },
                        "row": {
                            "type": "integer",
                            "description": "(set_table_cell) 行序号兜底（1 开始）",
                        },
                        "col": {
                            "type": "integer",
                            "description": "(set_table_cell) 列序号兜底（1 开始）",
                        },
                        "heading": {
                            "type": "string",
                            "description": "(append_section) 新章节标题",
                        },
                        "level": {
                            "type": "integer",
                            "description": "(append_section) 标题级别 1-3，默认 2",
                        },
                        "body": {
                            "type": "string",
                            "description": "(append_section) 章节正文，支持 **粗**、`码`、[文](链) 行内语法",
                        },
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "(append_section) 列表条目",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "(append_section) 追加表格的表头",
                        },
                        "rows": {
                            "type": "array",
                            "description": "(append_section) 追加表格的数据行",
                        },
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["path", "ops"],
    },
)
class EditDocxAdapter(ToolAdapter):
    script_name = "edit_docx.py"
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
