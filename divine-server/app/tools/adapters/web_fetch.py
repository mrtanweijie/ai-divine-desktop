from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "web_fetch",
    "抓取指定网页或 URL 的网络内容并返回可读文本，用于浏览网页、资料查询等场景",
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "需要抓取的完整 URL，必须以 http:// 或 https:// 开头",
            }
        },
        "required": ["url"],
    },
)
class WebFetchAdapter(ToolAdapter):
    script_name = "web_fetch.py"
    category = "web"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"url": str(arguments.get("url") or "")}
