from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "document_outline",
    "查看 Word(.docx)/Excel(.xlsx)/PPT(.pptx) 文档的结构大纲，输出可编辑坐标："
    "docx 返回段落清单（index/样式/内容预览）与表格清单（序号/表头/行列数）；"
    "xlsx 返回 sheet 清单（名称/数据范围/表头/公式数）；pptx 返回页清单（页码/标题/文本预览/备注）。"
    "在使用 edit_docx 修改文档前先调用本工具定位目标段落或表格",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文档路径（workspace 相对路径或用户提供的绝对路径）",
            },
        },
        "required": ["path"],
    },
)
class DocumentOutlineAdapter(ToolAdapter):
    script_name = "document_outline.py"
    category = "documents"
    timeout = 30
    allow_external_paths = True

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
