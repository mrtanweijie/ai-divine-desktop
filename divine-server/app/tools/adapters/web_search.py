from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "web_search",
    "搜索互联网，返回与查询相关的网页标题、链接和摘要（默认 5 条，最多 10 条）；"
    "需要查找资料、获取最新信息、调研多个来源时优先使用本工具，"
    "需要读取具体页面全文时再配合 web_fetch / web_fetch_batch 使用",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题，中英文均可，越具体越好",
            },
            "max_results": {
                "type": "integer",
                "description": "可选，最多返回几条结果，默认 5，最大 10",
            },
        },
        "required": ["query"],
    },
)
class WebSearchAdapter(ToolAdapter):
    script_name = "web_search.py"
    category = "web"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        raw = arguments.get("max_results")
        try:
            max_results = (
                max(1, min(int(raw), 10)) if raw is not None else 5
            )
        except (TypeError, ValueError):
            max_results = 5
        return {"query": query, "max_results": max_results}
