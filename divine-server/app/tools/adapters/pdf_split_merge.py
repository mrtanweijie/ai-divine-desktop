from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pdf_split_merge",
    "拆分或合并 PDF 文件；merge 把多个 PDF 合并成一个，split 按页码提取或拆成单页",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["merge", "split"],
                "description": "merge 合并，split 拆分",
            },
            "file_path": {
                "type": "string",
                "description": "split 时的源 PDF 路径",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "merge 时待合并的 PDF 路径列表",
            },
            "output_path": {
                "type": "string",
                "description": "merge 或 split 提取页时的输出文件路径",
            },
            "output_dir": {
                "type": "string",
                "description": "split 全部页面时的输出目录",
            },
            "pages": {
                "type": "string",
                "description": "split 提取的页码，例如 1-3,5,7-9；省略则拆成单页",
            },
        },
        "required": ["action"],
    },
)
class PdfSplitMergeAdapter(ToolAdapter):
    script_name = "pdf_split_merge.py"
    category = "files"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": str(arguments.get("action") or ""),
            "file_path": str(arguments.get("file_path") or ""),
            "files": list(arguments.get("files") or []),
            "output_path": str(arguments.get("output_path") or ""),
            "output_dir": str(arguments.get("output_dir") or ""),
            "pages": str(arguments.get("pages") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        paths = []
        for key in ("file_path", "output_path", "output_dir"):
            external = resolve_external_path(workspace, arguments.get(key))
            if external:
                paths.append(external)
        for raw in arguments.get("files") or []:
            external = resolve_external_path(workspace, raw)
            if external:
                paths.append(external)
        return paths
