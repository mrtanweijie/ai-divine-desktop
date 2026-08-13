import ipaddress
import json
import socket
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_RESPONSE_BYTES = 2_000_000
MAX_URLS = 10
MAX_CONTENT_PER_SOURCE = 6000
MAX_TOTAL_CONTENT = 24000


def _accept_language(locale: str) -> str:
    return {
        "zh-CN": "zh-CN,zh;q=0.9",
        "zh-TW": "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
        "en": "en-US,en;q=0.9",
    }.get(locale, "zh-CN,zh;q=0.9")


def _text_content(text: str, content_type: str) -> str:
    content_type = content_type.lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return text[:MAX_CONTENT_PER_SOURCE]

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = (
        soup.title.get_text(strip=True)
        if soup.title and soup.title.get_text(strip=True)
        else ""
    )
    text = "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )
    links = [
        link.get("href")
        for link in soup.find_all("a", href=True)
        if str(link.get("href", "")).startswith(("http://", "https://"))
    ][:10]

    blocks = []
    if title:
        blocks.append(f"标题：{title}")
    blocks.append(text[:MAX_CONTENT_PER_SOURCE])
    if links:
        blocks.append("相关链接：\n" + "\n".join(links))
    return "\n\n".join(blocks)


def _is_private_ip(host: str) -> bool:
    raw = host.split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    addresses = {info[4][0] for info in infos}
    return not addresses or any(_is_private_ip(address) for address in addresses)


def _fetch(url: str, headers: dict[str, str]) -> tuple[str, str, bool]:
    current = url
    for _ in range(6):
        if _is_local_url(current):
            raise ValueError("不允许访问本地、内网或无法解析的地址")
        with httpx.Client(timeout=20.0, follow_redirects=False) as client:
            with client.stream("GET", current, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("重定向缺少 Location")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= MAX_RESPONSE_BYTES:
                        break
                raw = b"".join(chunks)[:MAX_RESPONSE_BYTES]
                return (
                    raw.decode("utf-8", errors="replace"),
                    content_type,
                    total > MAX_RESPONSE_BYTES,
                )
    raise ValueError("重定向次数过多")


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

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": _accept_language(locale),
    }
    sources: list[dict[str, object]] = []
    success_count = 0
    for url in urls[:max_results]:
        try:
            text, content_type, truncated = _fetch(url, headers)
            content = _text_content(text, content_type)
            sources.append(
                {
                    "url": url,
                    "success": True,
                    "message": "抓取成功",
                    "content": content,
                    "truncated": truncated,
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
