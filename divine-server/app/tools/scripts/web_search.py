"""web_search 工具：搜索互联网（无需 API Key），多后端容错。

后端策略（按顺序尝试，前者失败/无结果自动切换下一个）：
1. Bing（https://www.bing.com/search）—— 首选：国内可直连（自动跳转
   cn.bing.com），反爬较宽松，按 locale 设置 mkt 参数。
2. Baidu（https://www.baidu.com/s）—— zh 语言环境启用：国内内容覆盖较全
   （百家号/知乎/CSDN 等）；反爬较严，命中安全验证页时自动降级。
3. DuckDuckGo HTML（https://html.duckduckgo.com/html/）—— 境外环境兜底，
   大陆无法访问，且非官方接口可能触发反爬校验（脚本会检测并降级）。

输入（stdin JSON）: {workspace, output_dir, params: {query, max_results}, locale}
输出（stdout JSON）: {success, message, content, data: {query, count, results}}

每条结果包含标题、真实 URL 与摘要，供 Agent 判断后决定用
web_fetch / web_fetch_batch 读取具体页面。
"""

import base64
import json
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

BAIDU_ENDPOINT = "https://www.baidu.com/s"
BING_ENDPOINT = "https://www.bing.com/search"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
REQUEST_TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 10

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def _accept_language(locale: str) -> str:
    return {
        "zh-CN": "zh-CN,zh;q=0.9",
        "zh-TW": "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
        "en": "en-US,en;q=0.9",
    }.get(locale, "zh-CN,zh;q=0.9")


def _bing_market(locale: str) -> str:
    return {
        "zh-CN": "zh-CN",
        "zh-TW": "zh-TW",
        "en": "en-US",
    }.get(locale, "zh-CN")


def _decode_bing_url(href: str) -> str:
    """Bing 部分结果为 /ck/a 跳转链接，真实 URL 在 u 参数里。

    u 参数形如 "a1a<base64>"（部分情况不带 a1a 前缀），解码后应为 http(s) 链接；
    解码失败则退回原链接。
    """
    if not href or "/ck/a" not in href:
        return href
    candidates = parse_qs(urlparse(href).query).get("u")
    if not candidates:
        return href
    encoded = candidates[0]
    variants = [encoded]
    if encoded.startswith("a1a"):
        variants.append(encoded[3:])
    for variant in variants:
        try:
            decoded = base64.urlsafe_b64decode(
                variant + "=" * (-len(variant) % 4)
            ).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 — 解码失败就试下一个变体
            continue
        if decoded.startswith(("http://", "https://")):
            return decoded
    return href


def _parse_baidu_results(html: str, max_results: int) -> list[dict[str, str]]:
    """Baidu 结果：标题在 h3 a，真实 URL 在容器 div 的 mu 属性，摘要在 summary-text。"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for block in soup.select("div.c-container"):
        if len(results) >= max_results:
            break
        link = block.select_one("h3 a")
        if link is None:
            continue
        title = link.get_text(strip=True)
        url = (block.get("mu") or "").strip()
        if not url:
            url = (link.get("href") or "").strip()
        snippet_el = (
            block.select_one('span[class*="summary-text"]')
            or block.select_one(".c-abstract")
        )
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if not title and not url:
            continue
        results.append(
            {"title": title, "url": url, "snippet": snippet[:500]}
        )
    return results


def _parse_bing_results(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for block in soup.select("li.b_algo"):
        if len(results) >= max_results:
            break
        link = block.select_one("h2 a")
        snippet_el = block.select_one(".b_caption p") or block.select_one("p")
        title = link.get_text(strip=True) if link else ""
        url = _decode_bing_url(link.get("href") or "") if link else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if not title and not url:
            continue
        results.append(
            {"title": title, "url": url, "snippet": snippet[:500]}
        )
    return results


def _parse_ddg_results(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for block in soup.select(".result"):
        if len(results) >= max_results:
            break
        link = block.select_one(".result__a")
        snippet_el = block.select_one(".result__snippet")
        title = link.get_text(strip=True) if link else ""
        href = link.get("href") or "" if link else ""
        url = ""
        if href:
            candidates = parse_qs(urlparse(href).query).get("uddg")
            url = candidates[0] if candidates else href
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if not title and not url:
            continue
        results.append(
            {"title": title, "url": url, "snippet": snippet[:500]}
        )
    return results


def _get(url: str, headers: dict[str, str]) -> str:
    with httpx.Client(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.text[:MAX_RESPONSE_BYTES]


def _try_baidu(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    url = f"{BAIDU_ENDPOINT}?{urlencode({'wd': query})}"
    html = _get(url, headers)
    if "百度安全验证" in html or "wappass" in html.lower():
        return {"ok": False, "reason": "baidu_blocked"}
    results = _parse_baidu_results(html, max_results)
    if not results:
        return {"ok": False, "reason": "baidu_no_results"}
    return {"ok": True, "backend": "baidu", "results": results}


def _try_bing(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    url = f"{BING_ENDPOINT}?{urlencode({'q': query, 'mkt': _bing_market(locale)})}"
    html = _get(url, headers)
    if not html or "b_algo" not in html:
        return {"ok": False, "reason": "bing_no_results_or_blocked"}
    results = _parse_bing_results(html, max_results)
    if not results:
        return {"ok": False, "reason": "bing_no_results"}
    return {"ok": True, "backend": "bing", "results": results}


def _try_ddg(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    url = f"{DDG_ENDPOINT}?{urlencode({'q': query})}"
    html = _get(url, headers)
    if "anomaly" in html.lower() and ".result" not in html:
        return {"ok": False, "reason": "ddg_blocked"}
    results = _parse_ddg_results(html, max_results)
    if not results:
        return {"ok": False, "reason": "ddg_no_results"}
    return {"ok": True, "backend": "duckduckgo", "results": results}


def _search(query: str, max_results: int, locale: str) -> dict:
    # Bing 首选（国内可直连、反爬宽松）；zh 语言环境追加百度兜底（国内内容覆盖较全）。
    backends = (
        (_try_bing, _try_baidu, _try_ddg)
        if str(locale).lower().startswith("zh")
        else (_try_bing, _try_ddg)
    )
    errors: list[str] = []
    for attempt in backends:
        try:
            outcome = attempt(query, max_results, locale)
        except Exception as exc:  # noqa: BLE001 — 单个后端失败不阻断整体
            errors.append(f"{getattr(attempt, '__name__', 'backend')}: {exc}")
            continue
        if outcome.get("ok"):
            results = outcome["results"]
            backend = outcome["backend"]
            lines = [f"搜索「{query}」结果（来源：{backend}）："]
            for index, item in enumerate(results, start=1):
                lines.append(f"{index}. {item['title']}")
                if item["url"]:
                    lines.append(f"   链接: {item['url']}")
                if item["snippet"]:
                    lines.append(f"   摘要: {item['snippet']}")
            return {
                "success": True,
                "message": f"已搜索「{query}」，返回 {len(results)} 条结果",
                "content": "\n".join(lines),
                "data": {
                    "query": query,
                    "count": len(results),
                    "backend": backend,
                    "results": results,
                },
            }
        errors.append(outcome.get("reason", "unknown"))
    detail = "；".join(dict.fromkeys(errors)) or "所有搜索后端均不可用"
    return {
        "success": False,
        "message": f"搜索失败: {detail}",
    }


def main() -> None:
    data = json.load(sys.stdin)
    locale = str(data.get("locale") or "zh-CN")
    params = data.get("params") or {}
    query = str(params.get("query") or "").strip()
    if not query:
        print(json.dumps({"success": False, "message": "缺少搜索关键词 query"}))
        return
    try:
        max_results = int(params.get("max_results") or DEFAULT_MAX_RESULTS)
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS
    max_results = max(1, min(max_results, MAX_RESULTS_CAP))
    print(json.dumps(_search(query, max_results, locale), ensure_ascii=False))


if __name__ == "__main__":
    main()
