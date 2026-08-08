from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "clipboard",
    "读取、写入或清空系统剪贴板；读取时返回剪贴板文本内容，写入时可把指定内容放到剪贴板",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "clear"],
                "description": "read 读取剪贴板，write 写入内容，clear 清空剪贴板",
            },
            "content": {"type": "string", "description": "写入剪贴板的内容"},
        },
        "required": ["action"],
    },
)
class ClipboardAdapter(ToolAdapter):
    script_name = "clipboard.py"
    category = "system"
    timeout = 15

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": str(arguments.get("action") or "read"),
            "content": str(arguments.get("content") or ""),
        }
