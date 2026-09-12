from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "pptx_to_png",
    "把演示文稿每页渲染成 PNG 图片（无 LibreOffice 也能用）；用户要 PPT 的图片版、"
    "要把幻灯片导出成图、或说「转成 PNG」时使用。file_path 传当前 pptx/ppsx 文件路径，"
    "scale 可选（1.0 = 96dpi，默认 1.5），page 可选（只导出某一页），"
    "output_path 可选（输出目录）。旧版 .ppt 不支持。",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "当前 pptx / ppsx 文件路径，可传 workspace 相对或绝对路径",
            },
            "output_path": {
                "type": "string",
                "description": "输出目录，workspace 内相对路径；默认保存到应用输出目录 presentations/<文件名>-png",
            },
            "scale": {
                "type": "number",
                "description": "渲染倍率，1.0 = 96dpi；默认 1.5（16:9 得 2000×1125）",
            },
            "page": {
                "type": "integer",
                "description": "1 基页码；只导出该页，不传则导出全部页面",
            },
        },
        "required": ["file_path"],
    },
)
class PptxToPngAdapter(ToolAdapter):
    script_name = "pptx_to_png.py"
    category = "presentations"
    timeout = 120
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": str(arguments.get("file_path") or "").strip(),
            "output_path": str(arguments.get("output_path") or "").strip(),
            "scale": arguments.get("scale"),
            "page": arguments.get("page"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("file_path"))
        return [external] if external else []
