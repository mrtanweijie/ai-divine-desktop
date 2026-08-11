from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "edit_svg",
    "基于现有 SVG 修改；用户要求修改当前 SVG 时使用，file_path 传当前 SVG 文件路径，"
    "content 传完整更新后的 SVG 源码。只改用户指令中提到的元素，其他元素保持原样，不要重新生成。",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "当前 SVG 文件路径，可传 workspace 相对或绝对路径",
            },
            "content": {
                "type": "string",
                "description": "完整更新后的 SVG 源码，不要包含围栏代码块",
            },
        },
        "required": ["file_path", "content"],
    },
)
class EditSvgAdapter(ToolAdapter):
    script_name = "edit_svg.py"
    category = "svg"
    timeout = 20
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": str(arguments.get("file_path") or "").strip(),
            "content": str(arguments.get("content") or ""),
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
