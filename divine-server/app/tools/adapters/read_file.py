from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "read_file",
    "读取本地文件内容并返回给模型，支持 txt/md/json/csv/docx/pptx/pdf/xlsx/xlsm；"
    "支持 start_line/end_line 只读取部分行；读取 Excel 请使用本工具",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "workspace 内的相对或绝对路径",
            },
            "start_line": {
                "type": "integer",
                "description": "从第几行开始读取，从 1 开始，默认 1",
                "default": 1,
            },
            "end_line": {
                "type": "integer",
                "description": "读取到第几行（含），默认读取到末尾",
            },
        },
        "required": ["file_path"],
    },
)
class ReadFileAdapter(ToolAdapter):
    script_name = "read_file.py"
    category = "files"
    timeout = 30
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": arguments.get("file_path") or "",
            "start_line": arguments.get("start_line"),
            "end_line": arguments.get("end_line"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        raw = str(arguments.get("file_path") or "").strip()
        if not raw:
            return []
        path = Path(raw)
        if not path.is_absolute():
            path = workspace / path
        resolved = path.resolve()
        try:
            resolved.relative_to(workspace.resolve())
        except ValueError:
            return [str(resolved)]
        return []
