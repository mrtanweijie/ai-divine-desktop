"""web_fetch_batch 工具：批量抓取多个网页或数据源并汇总返回。

每个 URL 走双层策略：httpx 静态直连优先；空壳页（JS 动态渲染）自动
用本机无头浏览器渲染兜底。

输入（stdin JSON）: {workspace, output_dir, params: {urls, max_results}, locale}
输出（stdout JSON）: {success, message, content, data: {results, summary}}
每条 result 含 method 字段：static（静态抓取）| browser（浏览器渲染）
"""

from __future__ import annotations

import json
import os
import sys

# 冻结版 --run-script 不会像普通 `python script.py` 那样自动把脚本所在目录
# 加入 sys.path，需显式加入以支持兄弟模块 web_common 的导入。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import web_common
from web_common import (
    SPARSE_TEXT_THRESHOLD,
    build_headers,
    browser_fallback,
    is_sparse,
    static_fetch,
    text_content,
)

MAX_URLS = 10
MAX_CONTENT_PER_SOURCE = 6000
MAX_TOTAL_CONTENT = 24000
# 批量场景收紧浏览器预算：避免多个空壳页拖垮整体耗时
BATCH_LOAD_TIMEOUT = 10.0
BATCH_SETTLE = 1.0


def main() -> None:
    data = json.load(sys.stdin)
    locale = str(data.get("locale") or "zh-CN")
    params = data.get("params") or {}
    raw_urls = params.get("urls") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    urls = [str(url).strip() for url in raw_urls if str(url).strip()]
    if not urls:
        print(json.dumps({"success": False, "message": "缺少 URL 列表"}))
        return
    if len(urls) > MAX_URLS:
        urls = urls[:MAX_URLS]
    try:
        max_results = max(1, min(int(params.get("max_results") or MAX_URLS), MAX_URLS))
    except (TypeError, ValueError):
        max_results = MAX_URLS

    sources: list[dict[str, object]] = []
    success_count = 0
    for url in urls[:max_results]:
        print(
            json.dumps(
                {
                    "progress": True,
                    "index": len(sources),
                    "url": url,
                    "total": len(urls[:max_results]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        try:
            headers = build_headers(url, locale)
            text, content_type, truncated = static_fetch(url, headers)
            method = "static"
            content = text_content(text, content_type, MAX_CONTENT_PER_SOURCE)
            if is_sparse(text, content_type):
                fb_method, fb_payload = browser_fallback(
                    url, params, load_timeout=BATCH_LOAD_TIMEOUT, settle=BATCH_SETTLE
                )
                if fb_method == "api":
                    content = text_content(
                        json.dumps(fb_payload, ensure_ascii=False, indent=2),
                        "application/json",
                        MAX_CONTENT_PER_SOURCE,
                    )
                    method = "api"
                elif fb_method == "browser":
                    rendered = text_content(
                        fb_payload, "text/html", MAX_CONTENT_PER_SOURCE
                    )
                    if len(rendered.strip()) >= SPARSE_TEXT_THRESHOLD:
                        content = rendered
                        method = "browser"
                    # 渲染后仍空 → 保留静态结果
            sources.append(
                {
                    "url": url,
                    "success": True,
                    "message": "抓取成功",
                    "content": content,
                    "truncated": truncated,
                    "method": method,
                }
            )
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            sources.append(
                {"url": url, "success": False, "message": f"抓取失败: {exc}"}
            )

    summary = f"已抓取 {success_count}/{len(urls)} 个数据源"
    model_sources: list[dict[str, object]] = []
    total_chars = 0
    for source in sources:
        url = str(source.get("url") or "")
        body = (
            str(source.get("content") or "")
            if source.get("success")
            else str(source.get("message") or "")
        )
        remaining = MAX_TOTAL_CONTENT - total_chars
        if remaining <= 0:
            break
        item: dict[str, object] = {
            key: value for key, value in source.items() if key != "content"
        }
        item["content"] = body[:remaining]
        model_sources.append(item)
        total_chars += len(str(item["content"]))
    content = json.dumps(
        {
            "success": True,
            "message": summary,
            "sources": model_sources,
        },
        ensure_ascii=False,
    )
    print(
        json.dumps(
            {
                "success": True,
                "message": summary,
                "content": content,
                "data": {"results": sources, "summary": summary},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
