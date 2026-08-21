from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "read_image",
    "读取本地图片并识别内容，支持 jpg/png/webp/gif/bmp；优先使用免费 GLM 视觉模型，"
    "未配置 GLM 时回退到 deepseek-v4-flash-vision-exp",
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
