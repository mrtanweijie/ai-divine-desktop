from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "image_resize",
    "缩放本地图片并保存为新文件，支持 jpg/png/webp 等格式；可只给 width 或 height 保持宽高比",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "源图片路径"},
            "output_path": {
                "type": "string",
                "description": "输出路径，默认在源文件旁生成 _resized 文件",
            },
            "width": {"type": "integer", "description": "目标宽度"},
            "height": {"type": "integer", "description": "目标高度"},
            "quality": {
                "type": "integer",
                "description": "jpg/webp 压缩质量，1-100，默认 85",
            },
        },
        "required": ["file_path"],
    },
)
class ImageResizeAdapter(ToolAdapter):
    script_name = "image_resize.py"
    category = "files"
    timeout = 30
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": str(arguments.get("file_path") or ""),
            "output_path": str(arguments.get("output_path") or ""),
            "width": arguments.get("width"),
            "height": arguments.get("height"),
            "quality": arguments.get("quality"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        paths = []
        for key in ("file_path", "output_path"):
            external = resolve_external_path(workspace, arguments.get(key))
            if external:
                paths.append(external)
        return paths
