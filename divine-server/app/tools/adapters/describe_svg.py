from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "describe_svg",
    "读取现有 SVG 并返回画布尺寸、元素清单、关键 id 和结构摘要，供模型理解当前 SVG 后做精确编辑；"
    "可选 include_source 返回完整源码。",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "当前 SVG 文件路径，可传 workspace 相对或绝对路径",
            },
            "include_source": {
                "type": "boolean",
                "description": "是否同时返回完整 SVG 源码，默认 false",
            },
        },
        "required": ["file_path"],
    },
)
class DescribeSvgAdapter(ToolAdapter):
    script_name = "describe_svg.py"
    category = "svg"
    timeout = 20
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": str(arguments.get("file_path") or "").strip(),
            "include_source": bool(arguments.get("include_source") or False),
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
