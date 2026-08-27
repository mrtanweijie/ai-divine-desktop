from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "glob_files",
    "按 glob 模式匹配工作区文件路径，支持 ** 递归通配（如 src/**/*.test.ts、"
    "**/*.py、docs/*.md）；结果按修改时间新→旧排序并遵循 .gitignore。"
    "需要按文件名子串模糊查找时用 search_files，按内容搜索用 grep_files",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "glob 模式，如 \"src/**/*.ts\"、\"**/*_test.go\"、"
                    "\"*.json\"；** 匹配任意层级目录"
                ),
            },
            "path": {
                "type": "string",
                "description": "workspace 内要搜索的相对目录，默认整个工作区",
            },
        },
        "required": ["pattern"],
    },
)
class GlobFilesAdapter(ToolAdapter):
    script_name = "glob_files.py"
    category = "files"
    timeout = 20

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": str(arguments.get("pattern") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }
