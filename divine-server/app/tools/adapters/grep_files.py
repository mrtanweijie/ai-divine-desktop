from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "grep_files",
    "按内容搜索工作区中的文本文件（正则匹配），返回每个命中的文件、行号和行内容；"
    "支持 glob 过滤、上下文行、大小写开关；自动尊重 .gitignore 并跳过二进制/超大文件。"
    "定位代码（函数定义、配置项、报错关键字）时优先使用本工具，search_files 只按文件名搜索。",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要搜索的正则表达式，例如 def foo|api_key",
            },
            "path": {
                "type": "string",
                "description": "workspace 内要搜索的相对目录，默认搜索整个工作区",
            },
            "glob": {
                "type": "string",
                "description": "可选文件过滤，如 *.py、src/**/*.ts",
            },
            "context": {
                "type": "integer",
                "description": "每个命中前后各带多少行上下文，默认 0，最大 10",
                "default": 0,
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "是否区分大小写，默认 false",
                "default": False,
            },
            "include_hidden": {
                "type": "boolean",
                "description": "是否搜索隐藏文件/目录，默认 false",
                "default": False,
            },
            "max_results": {
                "type": "integer",
                "description": "最多返回多少条命中，默认 200，最大 500",
                "default": 200,
            },
        },
        "required": ["pattern"],
    },
)
class GrepFilesAdapter(ToolAdapter):
    script_name = "grep_files.py"
    category = "files"
    timeout = 30
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": str(arguments.get("pattern") or ""),
            "path": str(arguments.get("path") or "").strip(),
            "glob": str(arguments.get("glob") or "").strip() or None,
            "context": arguments.get("context"),
            "case_sensitive": bool(arguments.get("case_sensitive")),
            "include_hidden": bool(arguments.get("include_hidden")),
            "max_results": arguments.get("max_results"),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("path"))
        return [external] if external else []
