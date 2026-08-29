"""web_search 工具：搜索互联网（无需 API Key），多后端容错。

后端策略（按顺序尝试，前者失败/无结果/结果未命中主题时自动切换下一个）：
1. Bing（https://www.bing.com/search）—— 首选：国内可直连（自动跳转
   cn.bing.com），反爬较宽松，按 locale 设置 mkt 参数。
2. Baidu（https://www.baidu.com/s）—— zh 语言环境启用：国内内容覆盖较全
   （百家号/知乎/CSDN 等）；反爬较严，命中安全验证页时自动降级；搜索前先
   预热首页拿 BAIDUID cookie 降低拦截概率。
3. Sogou（https://www.sogou.com/web）—— zh 语言环境启用：中文新鲜内容
   （直播吧/头条等）收录好，弥补 Bing 对中文实时内容收录滞后的短板。
4. 360（https://www.so.com/s）—— zh 语言环境启用：中文资讯/新闻类收录好，
   结果带 data-mdurl 真实地址。
5. DuckDuckGo HTML（https://html.duckduckgo.com/html/）—— 境外环境兜底，
   大陆无法访问，且非官方接口可能触发反爬校验（脚本会检测并降级）。

结果质量校验：每个后端返回后，校验结果标题/URL 是否覆盖查询核心词
（剔除引号/OR/site: 后的关键词，去停用词/纯数字/比分形态）；未命中主题
则视为该后端无效，继续尝试下一个后端——避免"返回了结果但全是百科/官网
通用页"的假成功。

输入（stdin JSON）: {workspace, output_dir, params: {query, max_results}, locale}
输出（stdout JSON）: {success, message, content, data: {query, count, backend, results}}

每条结果包含标题、真实 URL 与摘要，供 Agent 判断后决定用
web_fetch / web_fetch_batch 读取具体页面。
"""

import base64
import json
import re
import sys
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

BAIDU_ENDPOINT = "https://www.baidu.com/s"
BING_ENDPOINT = "https://www.bing.com/search"
SOGOU_ENDPOINT = "https://www.sogou.com/web"
SO360_ENDPOINT = "https://www.so.com/s"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
REQUEST_TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 10

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# 结果相关性校验：这些词不算核心词（搜索意图词，引擎不一定回显）
STOPWORD_TOKENS = {
    "战报", "比分", "赛果", "结果", "最新", "今日", "今天", "直播",
    "视频", "回顾", "复盘", "比赛", "资讯", "新闻", "信息", "详情",
}


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


def _clean_query(query: str) -> str:
    """清洗对 HTML 搜索引擎无效甚至有害的语法：引号、布尔操作符、site: 等。

    例：`"TES" "LGD" esports.op.gg OR scoregg 战报` → `TES LGD esports.op.gg scoregg 战报`
    """
    q = query.strip()
    q = re.sub(r'["\'`]', "", q)
    q = re.sub(r"\bsite\s*:\s*\S+", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\b(?:OR|AND|NOT)\b", " ", q, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", q).strip()


def _core_tokens(query: str) -> list[str]:
    """提取结果相关性校验用的核心词：去停用词、纯数字（年份）、比分形态（2-3/3:2）。"""
    tokens: list[str] = []
    for tok in re.split(r"\s+", _clean_query(query)):
        tok = tok.strip()
        if not tok or len(tok) < 2:
            continue
        if tok in STOPWORD_TOKENS:
            continue
        if re.fullmatch(r"\d+", tok):
            continue
        if re.fullmatch(r"\d+\s*[-:：]\s*\d+", tok):
            continue
        tokens.append(tok)
    return tokens


def _results_relevant(results: list[dict[str, str]], query: str) -> bool:
    """结果是否命中查询主题：至少 2 个核心词出现在结果标题/URL 里（核心词只有一个时
    需命中 1 个）。不满足说明该后端返回的是百科/官网等通用页，未真正覆盖主题。"""
    core = _core_tokens(query)
    if not core:
        return True
    haystack = " ".join(
        f"{item.get('title', '')} {item.get('url', '')}" for item in results
    ).lower()
    present = sum(1 for tok in core if tok.lower() in haystack)
    return present >= (2 if len(core) >= 2 else 1)


def _decode_redirect_url(href: str, base: str) -> str:
    """解码搜索引擎跳转链接，还原真实 URL。

    支持（含绝对 URL 形式，如 360 的 https://www.so.com/link?m=...）：
    - Bing /ck/a：u 参数为 base64url（可能带 a1a 前缀）
    - Sogou /link：url 参数为 base64url
    - 360 /link：m 参数为 base64url（部分结果带 data-mdurl，优先用 data-mdurl）
    仅当路径是已知跳转路径（/link、/ck/a）时才解码，避免误伤普通带
    u/url/m 参数的链接；解码失败或结果非 http(s) 时退回原链接
    （相对链接拼上 base）。
    """
    if not href:
        return href
    parsed = urlparse(href)
    is_redirect_path = "/ck/a" in parsed.path or parsed.path.rstrip("/") == "/link"
    if is_redirect_path:
        candidates = (
            parse_qs(parsed.query).get("u")
            or parse_qs(parsed.query).get("url")
            or parse_qs(parsed.query).get("m")
        )
        if candidates:
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
    if parsed.scheme in ("http", "https"):
        return href
    return urljoin(base, href)


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
        url = _decode_redirect_url(link.get("href") or "", BING_ENDPOINT) if link else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if not title and not url:
            continue
        results.append(
            {"title": title, "url": url, "snippet": snippet[:500]}
        )
    return results


def _parse_sogou_results(html: str, max_results: int) -> list[dict[str, str]]:
    """Sogou 结果：vrwrap 容器 + h3.vr-title a，链接为 /link?url= base64 跳转。"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for block in soup.select("div.vrwrap"):
        if len(results) >= max_results:
            break
        link = block.select_one("h3.vr-title a")
        if link is None:
            continue
        title = link.get_text(strip=True)
        url = _decode_redirect_url(link.get("href") or "", SOGOU_ENDPOINT)
        snippet_el = block.select_one("div.fz-mid") or block.select_one(".space-txt")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if not title and not url:
            continue
        results.append(
            {"title": title, "url": url, "snippet": snippet[:500]}
        )
    return results


def _parse_360_results(html: str, max_results: int) -> list[dict[str, str]]:
    """360 结果：li.res-list + h3.res-title a；data-mdurl 直接给真实 URL。"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for block in soup.select("li.res-list"):
        if len(results) >= max_results:
            break
        link = block.select_one("h3.res-title a")
        if link is None:
            continue
        title = link.get_text(strip=True)
        url = (link.get("data-mdurl") or "").strip()
        if not url:
            url = _decode_redirect_url(link.get("href") or "", SO360_ENDPOINT)
        snippet_el = block.select_one(".res-rich") or block.select_one("p")
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


def _get(url: str, headers: dict[str, str], client: httpx.Client | None = None) -> str:
    if client is None:
        client = httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True)
    response = client.get(url, headers=headers)
    response.raise_for_status()
    return response.text[:MAX_RESPONSE_BYTES]


def _try_baidu(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        # 预热首页拿 BAIDUID cookie，降低"百度安全验证"拦截概率
        try:
            client.get("https://www.baidu.com/", headers=headers)
        except httpx.HTTPError:
            pass
        url = f"{BAIDU_ENDPOINT}?{urlencode({'wd': query})}"
        try:
            html = _get(url, headers, client)
        except httpx.HTTPError:
            return {"ok": False, "reason": "baidu_request_failed"}
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


def _try_sogou(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    url = f"{SOGOU_ENDPOINT}?{urlencode({'query': query})}"
    html = _get(url, headers)
    if not html or 'class="vrwrap"' not in html:
        return {"ok": False, "reason": "sogou_no_results_or_blocked"}
    results = _parse_sogou_results(html, max_results)
    if not results:
        return {"ok": False, "reason": "sogou_no_results"}
    return {"ok": True, "backend": "sogou", "results": results}


def _try_360(query: str, max_results: int, locale: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": _accept_language(locale),
    }
    url = f"{SO360_ENDPOINT}?{urlencode({'q': query})}"
    html = _get(url, headers)
    if not html or "res-list" not in html:
        return {"ok": False, "reason": "360_no_results_or_blocked"}
    results = _parse_360_results(html, max_results)
    if not results:
        return {"ok": False, "reason": "360_no_results"}
    return {"ok": True, "backend": "360", "results": results}


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
    cleaned = _clean_query(query)
    # zh 语言环境：Bing 优先，Baidu/Sogou/360 补中文新鲜内容；境外环境 Bing + DDG 兜底
    backends = (
        (_try_bing, _try_baidu, _try_sogou, _try_360, _try_ddg)
        if str(locale).lower().startswith("zh")
        else (_try_bing, _try_ddg, _try_sogou, _try_360)
    )
    errors: list[str] = []
    for attempt in backends:
        try:
            outcome = attempt(cleaned, max_results, locale)
        except Exception as exc:  # noqa: BLE001 — 单个后端失败不阻断整体
            errors.append(f"{getattr(attempt, '__name__', 'backend')}: {exc}")
            continue
        if not outcome.get("ok"):
            errors.append(str(outcome.get("reason", "unknown")))
            continue
        results = outcome["results"]
        backend = outcome["backend"]
        # 结果质量校验：未命中查询主题（全是百科/官网通用页）则视为无效，切下一个后端
        if not _results_relevant(results, cleaned):
            errors.append(f"{backend}: 结果未命中主题")
            continue
        lines = [f"搜索「{query}」结果（来源：{backend}）："]
        for index, item in enumerate(results, start=1):
            lines.append(f"{index}. {item['title']}")
            if item["url"]:
                lines.append(f"   链接: {item['url']}")
            if item.get("snippet"):
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
