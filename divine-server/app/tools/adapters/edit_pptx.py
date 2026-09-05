from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "edit_pptx",
    "编辑已有 PowerPoint(.pptx) 的文本：替换文字（run 级保格式，含组合形状与表格内文本）、"
    "替换指定页标题。只动文本，不改母版/版式/图表。"
    "ops 顺序执行，任一步定位失败整体中止且文件不变。"
    "外部路径文件会生成编辑副本，不修改原文件；workspace 内文件编辑前自动备份，可用 undo_last_turn 撤销",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（.pptx），workspace 相对路径或用户提供的绝对路径",
            },
            "ops": {
                "type": "array",
                "description": "操作序列，按顺序执行",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["replace_text", "set_title"],
                            "description": "操作类型",
                        },
                        "find": {
                            "type": "string",
                            "description": "(replace_text) 要查找的文本",
                        },
                        "replace": {
                            "type": "string",
                            "description": "(replace_text) 替换文本",
                        },
                        "all": {
                            "type": "boolean",
                            "description": "(replace_text) 替换全部命中，默认只替换第一处",
                        },
                        "slide": {
                            "type": "integer",
                            "description": "页序号（1 开始）；replace_text 不传时替换全部页面，set_title 必传",
                        },
                        "text": {
                            "type": "string",
                            "description": "(set_title) 新标题文本",
                        },
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["path", "ops"],
    },
)
class EditPptxAdapter(ToolAdapter):
    script_name = "edit_pptx.py"
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
