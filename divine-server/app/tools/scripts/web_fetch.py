"""web_fetch 工具：抓取指定网页/URL 并返回可读文本。

双层策略：httpx 静态直连优先；静态结果为空壳（JS 动态渲染）时自动用
本机无头浏览器渲染兜底。可选参数：
- api_fragment：页面数据接口 URL 片段，提供后优先监听接口响应直接取 JSON
- wait_selector：浏览器渲染后等待出现的 CSS 选择器（懒加载内容）

输入（stdin JSON）: {workspace, output_dir, params: {url, wait_selector?, api_fragment?}, locale}
输出（stdout JSON）: {success, message, url, content, truncated,
                      data: {url, method, truncated}}
method: static（静态抓取）| browser（浏览器渲染）| api（接口直取）
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse

# 冻结版 --run-script 不会像普通 `python script.py` 那样自动把脚本所在目录
# 加入 sys.path，需显式加入以支持兄弟模块 web_common 的导入。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import web_common
from web_common import (
    MAX_SINGLE_CONTENT,
    SPARSE_TEXT_THRESHOLD,
    build_headers,
    browser_fallback,
    is_sparse,
    static_fetch,
    text_content,
)

METHOD_LABELS = {
    "static": "静态抓取",
    "browser": "浏览器渲染",
    "api": "接口直取",
}


def main() -> None:
    data = json.load(sys.stdin)
    locale = str(data.get("locale") or "zh-CN")
    params = data.get("params") or {}
    url = (params.get("url") or "").strip()
    if not url:
        print(json.dumps({"success": False, "message": "缺少 URL"}))
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "URL 无效，请使用 http/https 开头的完整地址",
                }
            )
        )
        return

    headers = build_headers(url, locale)
    try:
        text, content_type, truncated = static_fetch(url, headers)
        method = "static"
        content = text_content(text, content_type, MAX_SINGLE_CONTENT)
        note = ""
        api_fragment = str(params.get("api_fragment") or "").strip()
        wait_selector = str(params.get("wait_selector") or "").strip()
        if api_fragment or wait_selector or is_sparse(text, content_type):
            fb_method, fb_payload = browser_fallback(url, params)
            if fb_method == "api":
                content = text_content(
                    json.dumps(fb_payload, ensure_ascii=False, indent=2),
                    "application/json",
                    MAX_SINGLE_CONTENT,
                )
                method = "api"
            elif fb_method == "browser":
                rendered = text_content(fb_payload, "text/html", MAX_SINGLE_CONTENT)
                if len(rendered.strip()) < SPARSE_TEXT_THRESHOLD:
                    note = "；浏览器渲染后正文仍为空，页面可能需要登录或接口鉴权"
                else:
                    content = rendered
                    method = "browser"
            else:
                note = f"；{fb_payload}"
        message = f"已抓取 {url}（{METHOD_LABELS.get(method, method)}）"
        if note:
            message += note
        print(
            json.dumps(
                {
                    "success": True,
                    "message": message,
                    "url": url,
                    "content": content,
                    "truncated": truncated,
                    "data": {"url": url, "method": method, "truncated": truncated},
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"抓取失败: {exc}"},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
