from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "image_generate",
    "生成图片：根据文本描述生成图片。支持 MiniMax（文生图/图生图）和 GLM-Image（智谱，文生图，擅长文字密集场景如海报/PPT）两个后端",
    {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "图片描述（MiniMax ≤1500 字符，GLM ≤1000 字符，超长会自动截断）。"
                    "调用前必须主动压缩到 1000 字符以内："
                    "只保留主体、动作、场景、风格、色调等核心要素，"
                    "去掉形容词堆砌、重复细节和模板冗余文字。"
                ),
            },
            "provider": {
                "type": "string",
                "description": "图片生成后端：minimax（默认，支持文生图+图生图）/ glm（GLM-Image 智谱，擅长文字密集场景如海报/科普图/社交媒体图文）",
            },
            "aspect_ratio": {
                "type": "string",
                "description": "图片宽高比：1:1 / 16:9 / 9:16 / 21:9 / 2:3 / 3:2 / 4:3 / 3:4，默认 1:1。GLM 后端会自动映射为推荐尺寸",
            },
            "size": {
                "type": "string",
                "description": "GLM-Image 专用：输出尺寸如 1280x1280（需 32 倍数，512-2048px）。指定后忽略 aspect_ratio。可选值：1280x1280, 1568x1056, 1056x1568, 1472x1088, 1088x1472, 1728x960, 960x1728",
            },
            "reference_image": {
                "type": "string",
                "description": "参考图（图生图，仅 MiniMax 支持）：网络图片 URL 或本地路径，可选",
            },
            "filename": {
                "type": "string",
                "description": "输出文件名（不含扩展名自动补 .jpeg），默认自动命名",
            },
            "n": {
                "type": "integer",
                "description": "生成图片数量，1-4（GLM 仅支持 1），默认 1",
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "是否自动优化提示词（仅 MiniMax），默认 true",
            },
            "model": {
                "type": "string",
                "description": "模型名。MiniMax 默认 image-01；GLM 固定 glm-image",
            },
        },
        "required": ["prompt"],
    },
)
class ImageGenerateAdapter(ToolAdapter):
    script_name = "image_generate.py"
    category = "files"
    timeout = 150
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "prompt": str(arguments.get("prompt") or ""),
            "provider": str(arguments.get("provider") or ""),
            "aspect_ratio": str(arguments.get("aspect_ratio") or ""),
            "size": str(arguments.get("size") or ""),
            "reference_image": str(arguments.get("reference_image") or ""),
            "filename": str(arguments.get("filename") or ""),
            "model": str(arguments.get("model") or ""),
            "n": arguments.get("n"),
            "prompt_optimizer": arguments.get("prompt_optimizer"),
        }
        return params

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(
            workspace, arguments.get("reference_image")
        )
        return [external] if external else []
