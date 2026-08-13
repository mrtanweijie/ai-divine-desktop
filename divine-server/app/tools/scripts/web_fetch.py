import ipaddress
import json
import socket
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_RESPONSE_BYTES = 2_000_000


def _accept_language(locale: str) -> str:
    return {
        "zh-CN": "zh-CN,zh;q=0.9",
        "zh-TW": "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
        "en": "en-US,en;q=0.9",
    }.get(locale, "zh-CN,zh;q=0.9")


def _text_content(text: str, content_type: str) -> str:
    content_type = content_type.lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return text[:12000]

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
    blocks.append(text[:12000])
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

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": _accept_language(locale),
    }
    try:
        text, content_type, truncated = _fetch(url, headers)
        content = _text_content(text, content_type)
        print(
            json.dumps(
                {
                    "success": True,
                    "message": f"已抓取 {url}",
                    "url": url,
                    "content": content,
                    "truncated": truncated,
                    "data": {"url": url, "truncated": truncated},
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
