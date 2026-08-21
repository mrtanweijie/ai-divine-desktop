from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "svg_to_png_batch",
    "把 SVG 导出为多个不同尺寸的 PNG（iOS/Android 图标等）；sizes 传尺寸列表，"
    "file_path 传当前 SVG 文件路径，prefix 可选文件名前缀。",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "当前 SVG 文件路径，可传 workspace 相对或绝对路径",
            },
            "sizes": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "需要导出的 PNG 尺寸列表；未传时使用 iOS 全套尺寸",
            },
            "prefix": {
                "type": "string",
                "description": "可选，文件名前缀；默认使用 SVG 文件名",
            },
        },
        "required": ["file_path"],
    },
)
class SvgToPngBatchAdapter(ToolAdapter):
    script_name = "svg_to_png_batch.py"
    category = "svg"
    timeout = 120
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_sizes = arguments.get("sizes") or []
        if isinstance(raw_sizes, int):
            raw_sizes = [raw_sizes]
        try:
            sizes = [int(size) for size in raw_sizes if int(size) > 0]
        except (TypeError, ValueError):
            sizes = []
        return {
            "file_path": str(arguments.get("file_path") or "").strip(),
            "sizes": sizes[:30],
            "prefix": str(arguments.get("prefix") or "").strip(),
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
