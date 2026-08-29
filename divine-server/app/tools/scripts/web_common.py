"""web_fetch / web_fetch_batch 共享逻辑。

抓取策略（双层）：
1. 静态直连：httpx 拉取 HTML/JSON，带 SSRF 防护、重定向处理、限频退避。
2. 浏览器兜底：静态结果为"空壳"（可见正文过短，典型 JS 动态渲染）时，
   复用本机 Chrome/Edge 无头渲染后再提取；也可通过 api_fragment 参数
   直接监听页面数据接口的 JSON 响应。

DrissionPage 为可选依赖：未安装或启动失败时自动降级为静态结果，
不影响工具主流程。
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_RESPONSE_BYTES = 2_000_000
STATIC_TIMEOUT = 12.0
MAX_REDIRECTS = 6
MAX_STATIC_RETRIES = 1
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_SINGLE_CONTENT = 12000
# 可见正文低于该阈值 → 判定为 JS 渲染空壳页，触发浏览器兜底
SPARSE_TEXT_THRESHOLD = 80
# SPA 壳阈值：页面含前端框架挂载点（Next.js/Nuxt/CRA/Vite 等）且可见文本
# 仍偏少（主要是 SSR 的导航/页脚，正文异步加载）→ 同样判定为壳
SPA_SHELL_TEXT_THRESHOLD = 2000
_SPA_MOUNT_RE = re.compile(
    r"\bid\s*=\s*[\"'](__next|__nuxt|root|app|app-root|__gatsby)[\"']",
    re.IGNORECASE,
)
# 无头浏览器会被 CloudFront 等按 UA 拦截（HeadlessChrome 标记），统一用
# 普通 Chrome UA 覆盖，保证 JS 页面能真正渲染
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# DrissionPage 可选依赖：缺失时跳过浏览器兜底，静态抓取照常返回
BROWSER_AVAILABLE = True
try:
    from DrissionPage import ChromiumOptions, ChromiumPage  # type: ignore
except Exception:  # noqa: BLE001 — 可选依赖，缺失时降级为静态抓取
    ChromiumOptions = None
    ChromiumPage = None
    BROWSER_AVAILABLE = False


def accept_language(locale: str) -> str:
    return {
        "zh-CN": "zh-CN,zh;q=0.9",
        "zh-TW": "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
        "en": "en-US,en;q=0.9",
    }.get(locale, "zh-CN,zh;q=0.9")


def build_headers(url: str, locale: str) -> dict[str, str]:
    """浏览器风格请求头；Referer 取目标站自身 origin，避免跨站伪造来源触发风控。"""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "User-Agent": BROWSER_UA,
        "Accept-Language": accept_language(locale),
        "Referer": origin,
    }


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


def is_local_url(url: str) -> bool:
    """拦截本地/内网/无法解析的地址（SSRF 防护）。"""
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


def static_fetch(url: str, headers: dict[str, str]) -> tuple[str, str, bool]:
    """静态直连：跟随重定向（最多 6 跳），429/5xx 退避重试，限流 2MB。

    返回 (文本, content-type, 是否被截断)。
    """
    current = url
    retries = 0
    for _ in range(MAX_REDIRECTS):
        if is_local_url(current):
            raise ValueError("不允许访问本地、内网或无法解析的地址")
        with httpx.Client(timeout=STATIC_TIMEOUT, follow_redirects=False) as client:
            with client.stream("GET", current, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("重定向缺少 Location")
                    current = urljoin(current, location)
                    continue
                if (
                    response.status_code in RETRYABLE_STATUS
                    and retries < MAX_STATIC_RETRIES
                ):
                    retries += 1
                    time.sleep(1.0 * retries)
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
    raise ValueError("重定向次数过多或服务端持续异常")


def _html_to_text(text: str, max_chars: int) -> str:
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = (
        soup.title.get_text(strip=True)
        if soup.title and soup.title.get_text(strip=True)
        else ""
    )
    body = "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )
    links = [
        link.get("href")
        for link in soup.find_all("a", href=True)
        if str(link.get("href", "")).startswith(("http://", "https://"))
    ][:10]

    blocks: list[str] = []
    if title:
        blocks.append(f"标题：{title}")
    blocks.append(body[:max_chars])
    if links:
        blocks.append("相关链接：\n" + "\n".join(links))
    return "\n\n".join(blocks)


def text_content(text: str, content_type: str, max_chars: int = MAX_SINGLE_CONTENT) -> str:
    """按 content-type 提取可读文本；JSON 响应美化缩进输出。"""
    content_type = content_type.lower()
    if "text/html" in content_type or "application/xhtml" in content_type:
        return _html_to_text(text, max_chars)
    if "json" in content_type:
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)[:max_chars]
        except ValueError:
            return text[:max_chars]
    return text[:max_chars]


def is_sparse(text: str, content_type: str) -> bool:
    """空壳检测：HTML 页面可见正文过短（剔除 script/style 等），判定为
    JS 动态渲染或纯重定向页，需要浏览器兜底。

    两类判定：
    1. 可见文本 < 80 字符（纯壳/重定向页）；
    2. 页面含前端框架挂载点（Next.js/Nuxt/CRA/Vite 等）且可见文本仍
       < 2000 字符——此时正文几乎都是 SSR 的导航/页脚，核心数据异步加载
       （如 OP.GG 这类站点，静态抓取只有导航外壳）。
    """
    content_type = content_type.lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return False
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    visible = "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )
    if len(visible) < SPARSE_TEXT_THRESHOLD:
        return True
    if len(visible) < SPA_SHELL_TEXT_THRESHOLD and _SPA_MOUNT_RE.search(text):
        return True
    return False


class BrowserFallback:
    """复用本机 Chrome/Edge 的无头渲染兜底（惰性启动，用完即关）。

    - fetch_rendered: 打开页面，等待渲染后返回完整 DOM HTML；
      wait_selector 用于懒加载内容（等元素出现）。
    - fetch_api_json: 监听页面数据接口（URL 含 fragment）的网络响应，
      直接返回解析后的 JSON。
    """

    def __init__(self, load_timeout: float = 15.0, settle: float = 1.5) -> None:
        self._page = None
        self._load_timeout = load_timeout
        self._settle = settle

    def _ensure_page(self):  # noqa: ANN202 — ChromiumPage 可能为 None（可选依赖）
        if self._page is None:
            if not BROWSER_AVAILABLE:
                raise RuntimeError("未安装 DrissionPage，浏览器渲染兜底不可用")
            co = ChromiumOptions()
            co.headless(True)
            co.set_user_agent(BROWSER_UA)  # 覆盖 HeadlessChrome 标记，防 UA 反爬
            co.set_argument("--disable-gpu")
            co.set_argument("--no-first-run")
            co.set_argument("--disable-crash-reporter")
            co.set_argument("--disable-blink-features=AutomationControlled")
            co.set_argument("--window-size=1280,900")
            self._page = ChromiumPage(co)
        return self._page

    def fetch_rendered(self, url: str, wait_selector: str | None = None) -> str:
        page = self._ensure_page()
        page.get(url, timeout=self._load_timeout)
        try:
            page.wait.doc_loaded(timeout=self._load_timeout)
        except Exception:  # noqa: BLE001 — 加载超时也继续取当前 DOM
            pass
        if wait_selector:
            try:
                page.wait.ele_displayed(wait_selector, timeout=min(self._load_timeout, 10))
            except Exception:  # noqa: BLE001 — 元素未出现不阻塞，按已渲染内容返回
                pass
        if self._settle > 0:
            time.sleep(self._settle)
        return page.html

    def fetch_api_json(self, url: str, fragment: str) -> dict | list:
        """监听页面数据接口（URL 含 fragment）的网络响应，返回解析后的 JSON。

        页面可能先发多个非目标/非 JSON 请求，因此在整个时间预算内轮询
        匹配到的数据包，直到拿到第一个可解析为 JSON 的响应。
        """
        page = self._ensure_page()
        page.listen.start(fragment)
        try:
            page.get(url, timeout=self._load_timeout)
            deadline = time.monotonic() + self._load_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"{self._load_timeout:.0f}s 内未捕获到包含 {fragment!r} 的 JSON 响应"
                    )
                packet = page.listen.wait(count=1, timeout=remaining)
                if not packet:  # DrissionPage 超时返回 False 而非 None
                    raise RuntimeError(
                        f"{self._load_timeout:.0f}s 内未捕获到包含 {fragment!r} 的接口响应"
                    )
                body = packet.response.body
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                if isinstance(body, (dict, list)):
                    return body
                if isinstance(body, str):
                    body = body.strip()
                    if body.startswith(("{", "[")):
                        try:
                            return json.loads(body)
                        except ValueError:
                            continue
                # 非 JSON 响应（如 403 页/图片），继续等下一个匹配包
        finally:
            page.listen.stop()

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.quit()
            except Exception:  # noqa: BLE001
                pass
            self._page = None


def browser_fallback(
    url: str,
    params: dict,
    load_timeout: float = 15.0,
    settle: float = 1.5,
) -> tuple[str | None, object]:
    """浏览器兜底编排：优先按 api_fragment 抓接口 JSON，其次渲染取 DOM。

    返回 (method, payload)：method ∈ {"api", "browser"}，payload 为
    原始 JSON 对象或渲染后的 HTML；失败返回 (None, 错误信息字符串)。
    """
    if not BROWSER_AVAILABLE:
        return None, "未安装 DrissionPage，浏览器渲染兜底不可用"
    api_fragment = str(params.get("api_fragment") or "").strip()
    wait_selector = str(params.get("wait_selector") or "").strip()
    fb = BrowserFallback(load_timeout=load_timeout, settle=settle)
    try:
        if api_fragment:
            data = fb.fetch_api_json(url, api_fragment)
            return "api", data
        html = fb.fetch_rendered(url, wait_selector=wait_selector or None)
        return "browser", html
    except Exception as exc:  # noqa: BLE001
        return None, f"浏览器兜底失败: {exc}"
    finally:
        fb.close()
