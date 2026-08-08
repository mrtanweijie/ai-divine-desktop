import json
import sys
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


def _text_content(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return response.text[:12000]

    soup = BeautifulSoup(response.text, "html.parser")
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


def main() -> None:
    data = json.load(sys.stdin)
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
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content = _text_content(response)
        print(
            json.dumps(
                {
                    "success": True,
                    "message": f"已抓取 {url}",
                    "url": url,
                    "content": content,
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
