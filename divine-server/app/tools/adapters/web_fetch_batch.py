from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "web_fetch_batch",
    "批量抓取多个网页或数据源 URL 并汇总返回内容；当需要同时获取多个 URL"
    "（如多个指数、多个新闻源、多个页面）时使用，不要逐个重复调用 web_fetch",
    {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要抓取的完整 URL 列表，最多 10 个",
            },
            "max_results": {
                "type": "integer",
                "description": "可选，最多返回几个来源，默认全部",
            },
        },
        "required": ["urls"],
    },
)
class WebFetchBatchAdapter(ToolAdapter):
    script_name = "web_fetch_batch.py"
    category = "web"
    timeout = 120

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_urls = arguments.get("urls") or []
        if isinstance(raw_urls, str):
            raw_urls = [raw_urls]
        urls = [str(url).strip() for url in raw_urls if str(url).strip()]
        try:
            max_results = int(arguments.get("max_results") or 10)
        except (TypeError, ValueError):
            max_results = 10
        return {"urls": urls[:10], "max_results": max_results}
