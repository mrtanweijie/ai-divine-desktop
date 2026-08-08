from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "rag_search",
    "在工作区本地文本索引中检索相关内容，返回最匹配的文件分块和摘要；索引不存在时会先自动建立",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题或关键词"},
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认 5，最大 10",
            },
        },
        "required": ["query"],
    },
)
class RagSearchAdapter(ToolAdapter):
    script_name = "rag_search.py"
    category = "files"
    timeout = 30

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": str(arguments.get("query") or ""),
            "top_k": arguments.get("top_k"),
        }
