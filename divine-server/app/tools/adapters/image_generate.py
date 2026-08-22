from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "image_generate",
    "生成图片（MiniMax 文生图/图生图）：根据文本描述生成图片，"
    "或结合参考图生成保留主体特征的新图片",
    {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "图片描述（≤1500 字符，超长会自动截断）。"
                    "调用前必须主动压缩到 1500 字符以内："
                    "只保留主体、动作、场景、风格、色调等核心要素，"
                    "去掉形容词堆砌、重复细节和模板冗余文字。"
                ),
            },
            "aspect_ratio": {
                "type": "string",
                "description": "图片宽高比：1:1 / 16:9 / 9:16 / 21:9 / 2:3 / 3:2 / 4:3 / 3:4，默认 1:1",
            },
            "reference_image": {
                "type": "string",
                "description": "参考图（图生图）：网络图片 URL 或本地路径，可选",
            },
            "filename": {
                "type": "string",
                "description": "输出文件名（不含扩展名自动补 .jpeg），默认自动命名",
            },
            "n": {
                "type": "integer",
                "description": "生成图片数量，1-4，默认 1",
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "是否自动优化提示词，默认 true",
            },
            "model": {
                "type": "string",
                "description": "模型名，默认 image-01",
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
            "aspect_ratio": str(arguments.get("aspect_ratio") or ""),
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
