from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "terminal",
    "在本地终端执行系统命令并返回标准输出、错误输出和退出码；需要确认的命令会先征求用户同意。禁止用终端读取文件内容，文件读取请使用 read_file、spreadsheet、word_document 等专用工具",
    {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的终端命令",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录，默认使用当前工作区",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数，默认 30",
                "default": 30,
            },
        },
        "required": ["command"],
    },
)
class TerminalAdapter(ToolAdapter):
    script_name = "terminal.py"
    category = "system"
    timeout = 60
