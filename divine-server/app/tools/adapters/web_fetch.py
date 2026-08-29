from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "web_fetch",
    "抓取指定网页或 URL 的网络内容并返回可读文本；JS 动态渲染页面（静态抓取内容为空壳）"
    "会自动用本机浏览器渲染兜底，也支持监听页面数据接口直接获取 JSON",
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "需要抓取的完整 URL，必须以 http:// 或 https:// 开头",
            },
            "wait_selector": {
                "type": "string",
                "description": "可选，页面内容为懒加载/动态出现时，浏览器渲染后等待出现的 CSS"
                " 选择器（如 \"tbody tr\"），等元素出现后再提取内容",
            },
            "api_fragment": {
                "type": "string",
                "description": "可选，页面数据接口 URL 片段；提供后优先通过浏览器监听该接口"
                " 的网络响应，直接返回解析后的 JSON 数据",
            },
        },
        "required": ["url"],
    },
)
class WebFetchAdapter(ToolAdapter):
    script_name = "web_fetch.py"
    category = "web"
    timeout = 60

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {"url": str(arguments.get("url") or "")}
        for key in ("wait_selector", "api_fragment"):
            value = arguments.get(key)
            if value:
                params[key] = str(value)
        return params
