from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "read_image",
    "读取本地图片并用 GLM 视觉模型识别图片内容，支持 jpg/png/webp/gif/bmp",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "本地图片绝对路径，或 workspace 内的相对路径",
            }
        },
        "required": ["file_path"],
    },
)
class ReadImageAdapter(ToolAdapter):
    script_name = "read_image.py"
    category = "files"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"file_path": arguments.get("file_path") or ""}
