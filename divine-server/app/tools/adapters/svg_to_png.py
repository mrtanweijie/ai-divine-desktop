from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "svg_to_png",
    "把最终 SVG 导出为 PNG 位图；用户说导出/转 PNG/我要位图时使用，file_path 传当前 SVG 文件路径，"
    "width/height 可选，未传时按 SVG 原始尺寸导出。",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "当前 SVG 文件路径，可传 workspace 相对或绝对路径",
            },
            "output_path": {
                "type": "string",
                "description": "输出 PNG 路径；默认保存到 svg 输出目录",
            },
            "width": {"type": "integer", "description": "目标宽度，可选"},
            "height": {"type": "integer", "description": "目标高度，可选"},
        },
        "required": ["file_path"],
    },
)
class SvgToPngAdapter(ToolAdapter):
    script_name = "svg_to_png.py"
    category = "svg"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": str(arguments.get("file_path") or "").strip(),
            "output_path": str(arguments.get("output_path") or "").strip(),
            "width": arguments.get("width"),
            "height": arguments.get("height"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        paths = []
        for key in ("file_path", "output_path"):
            raw = str(arguments.get(key) or "").strip()
            if not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = workspace / path
            resolved = path.resolve()
            try:
                resolved.relative_to(workspace.resolve())
            except ValueError:
                paths.append(str(resolved))
        return paths
