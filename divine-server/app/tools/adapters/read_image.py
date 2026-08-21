from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "read_image",
    "读取图片并识别内容，支持 jpg/png/webp/gif/bmp；优先使用免费 GLM 视觉模型，"
    "未配置 GLM 时回退到 deepseek-v4-flash-vision-exp；file_path 传本地路径、"
    "url 传远程图片链接，二选一",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "本地图片绝对路径，或 workspace 内的相对路径",
            },
            "url": {
                "type": "string",
                "description": "远程图片链接（http/https），与 file_path 二选一",
            },
        },
    },
)
class ReadImageAdapter(ToolAdapter):
    script_name = "read_image.py"
    category = "files"
    timeout = 60
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = str(arguments.get("file_path") or "").strip()
        url = str(arguments.get("url") or "").strip()
        if not file_path and not url:
            raise ValueError("read_image 需要 file_path（本地路径）或 url（图片链接）")
        params: dict[str, Any] = {}
        if file_path:
            params["file_path"] = file_path
        if url:
            params["url"] = url
        return params

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
