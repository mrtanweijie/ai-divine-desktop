"""浏览器会话管理（031 §2 / §4）。

核心约定：
- **CDP attach 专用 profile**：Chrome 136+ 默认 user data dir 静默忽略调试端口，
  必须用独立 ``--user-data-dir``（引导创建，一次性登录持久复用）；
- **端口随机分配 + 端口发现**：不做固定 9222（本机任意进程可连、可读 cookie）；
  发现顺序：环境变量 → 引导启动写入的 endpoint 文件 → settings → 探测 9222（兼容旧引导）；
- **专属 tab**：每个聊天会话固定新建一个 tab，后续动作隐式定向该 tab；
- **懒启动 + 连接缓存**：首次用时才连接，同会话复用；断开清缓存（失败不缓存）。

测试可用环境变量 ``DIVINE_BROWSER_CDP_ENDPOINT`` 注入既有调试端点。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("divine.browser.session")

# endpoint 文件有效期：引导启动的浏览器不会常驻，超期视为失效
_ENDPOINT_FILE_TTL = 24 * 3600
_CONNECT_TIMEOUT = 10.0
_PROBE_TIMEOUT = 1.5
_DEFAULT_TIMEOUT_MS = 30_000

# 引导 UI 的"一键以调试模式启动"（031 §2）：专用 profile + 随机端口
_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def _canonical_endpoint_file() -> Path:
    """用户级固定位置：桌面 app（Application Support）与 dev shell（repo data）
    的 data_root 不同，端点文件必须落在与进程数据目录无关的路径上，
    所有进程才能一致发现。"""
    return Path.home() / ".divine" / "browser" / "cdp_endpoint.json"


def _endpoint_file() -> Path:
    # data_root() 是数据目录；data_dir() 是 DB 文件路径（DB_PATH 配置时），
    # 不能当目录用（会把 profile 建进 ai_divine.db/ 里）
    from ...config import data_root

    return data_root() / "browser" / "cdp_endpoint.json"


def _read_endpoint_file(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("ts") or 0) >= _ENDPOINT_FILE_TTL:
            return None
        url = str(payload.get("url") or "").strip()
        return url if url and _probe_endpoint(url) else None
    except Exception:  # noqa: BLE001 — 文件坏/超期都走后续发现路径
        return None


def _write_endpoint_file(url: str) -> None:
    """端点写入规范位置 + 当前 data_root 副本（尽力而为，失败不阻断）。"""
    payload = json.dumps({"url": url, "ts": time.time()}, ensure_ascii=False)
    canonical = _canonical_endpoint_file()
    try:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(payload, encoding="utf-8")
    except OSError:
        logger.warning("端点文件写入规范位置失败: %s", canonical)
    try:
        local = _endpoint_file()
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(payload, encoding="utf-8")
    except OSError:  # noqa: BLE001 — 副本失败可容忍
        pass


def _probe_endpoint(url: str) -> bool:
    try:
        response = httpx.get(f"{url.rstrip('/')}/json/version", timeout=_PROBE_TIMEOUT)
        return response.status_code == 200
    except Exception:  # noqa: BLE001 — 探测失败即不可用
        return False


def discover_cdp_endpoint() -> str | None:
    """按优先级发现本机 Chrome 调试端点；找不到返回 None。

    端点文件先读用户级规范位置（~/.divine/，跨进程一致），
    再读当前进程 data_root 副本。
    """
    import os

    env_endpoint = os.getenv("DIVINE_BROWSER_CDP_ENDPOINT", "").strip()
    if env_endpoint:
        return env_endpoint.rstrip("/")

    url = _read_endpoint_file(_canonical_endpoint_file())
    if url:
        return url.rstrip("/")
    url = _read_endpoint_file(_endpoint_file())
    if url:
        return url.rstrip("/")

    try:
        from ...config import settings_store

        port = int(settings_store.load().get("browser_cdp_port") or 0)
        if port > 0:
            url = f"http://127.0.0.1:{port}"
            if _probe_endpoint(url):
                return url
    except Exception:  # noqa: BLE001
        pass

    if _probe_endpoint("http://127.0.0.1:9222"):
        return "http://127.0.0.1:9222"
    return None


def launch_debug_chrome(force: bool = False) -> dict[str, Any]:
    """引导启动：专用 profile + 随机端口拉起 Chrome 调试模式，写入端点文件。

    已有可用端点时直接返回（force=True 跳过检查强制新启，用于连接异常的自愈）。
    返回 {url, pid, profile_dir, launched}；失败抛 RuntimeError。
    """
    if not force:
        existing = discover_cdp_endpoint()
        if existing:
            return {"url": existing, "pid": None, "launched": False}

    binary = next((Path(p) for p in _CHROME_CANDIDATES if Path(p).exists()), None)
    if binary is None:
        raise RuntimeError("未找到 Chrome/Chromium/Edge，请安装后再试")

    from ...config import data_root

    browser_dir = data_root() / "browser"
    profile_dir = browser_dir / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    port = random.randint(20000, 60000)
    process = subprocess.Popen(  # noqa: S603 — 固定二进制路径，参数为常量
        [
            str(binary),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # 脱离父进程组：引导启动方（CLI/一次性脚本）退出时不能连带杀掉浏览器，
        # 否则端点文件还在而 Chrome 已死，通道表现为随机 RuntimeError
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + _CONNECT_TIMEOUT
    while time.monotonic() < deadline:
        if _probe_endpoint(url):
            _write_endpoint_file(url)
            return {
                "url": url,
                "pid": process.pid,
                "profile_dir": str(profile_dir),
                "launched": True,
            }
        time.sleep(0.4)
    raise RuntimeError(f"Chrome 调试端口 {port} 启动超时")


class BrowserSession:
    """一个聊天会话对应的浏览器连接与专属 tab。"""

    def __init__(self, key: str) -> None:
        self.key = key
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self.confirmed = False
        # ref → {selector, role, name}；随快照重建（031 §4 ref 约定）
        self.refs: dict[str, dict[str, str]] = {}
        self.ref_counter = 0
        self.step_counter = 0

    # -- 连接 -------------------------------------------------------------
    async def _close_connection(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    async def ensure(self) -> Any:
        """返回专属 tab 的 Page；端点丢失或连接失效时自愈（引导启动）后重连。"""
        from playwright.async_api import async_playwright

        if self._page is not None:
            try:
                if not self._page.is_closed():
                    return self._page
            except Exception:  # noqa: BLE001
                pass
            self._page = None
        endpoint = discover_cdp_endpoint()
        if endpoint is None:
            # 自愈：引导启动专用浏览器（专用 profile + 随机端口），端点自动写盘。
            # 桌面端重启不会恢复独立运行的 Chrome——通道自愈只能靠这里。
            info = await asyncio.to_thread(launch_debug_chrome)
            endpoint = info["url"]
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                endpoint, timeout=_CONNECT_TIMEOUT * 1000
            )
        if not self._browser.contexts:
            # Playwright 经 CDP 不支持新建 context（报错表现为
            # Browser.setDownloadBehavior: Browser context management is not
            # supported）——context 为空说明浏览器处于异常状态，强制重启后重连一次
            await self._close_connection()
            await asyncio.to_thread(launch_debug_chrome, True)
            endpoint = discover_cdp_endpoint()
            if endpoint is None:
                raise RuntimeError(
                    "专用浏览器重启后仍未发现调试端口，请手动以调试模式启动 Chrome"
                )
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                endpoint, timeout=_CONNECT_TIMEOUT * 1000
            )
            if not self._browser.contexts:
                raise RuntimeError(
                    "专用浏览器连接异常（无可用上下文），请关闭所有该 profile 的 "
                    "Chrome 窗口后重试"
                )
        self._page = await self._browser.contexts[0].new_page()
        self._page.set_default_timeout(_DEFAULT_TIMEOUT_MS)
        return self._page

    @property
    def connected(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    def next_ref(self) -> str:
        """会话内单调递增的 ref 编号：旧编号永不复用，防止指错元素。"""
        self.ref_counter += 1
        return f"e{self.ref_counter}"

    async def page_meta(self) -> dict[str, str]:
        if self._page is None or self._page.is_closed():
            return {"url": "", "title": ""}
        try:
            return {"url": self._page.url, "title": await self._page.title()}
        except Exception:  # noqa: BLE001
            return {"url": "", "title": ""}

    async def close(self) -> None:
        if self._page is not None:
            try:
                await self._page.close()
            except Exception:  # noqa: BLE001
                pass
            self._page = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
        self.refs.clear()
        self.confirmed = False


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    def get(self, key: str) -> BrowserSession:
        """同 key 复用；取不到（或之前断开）就新建，失败不缓存。"""
        return self._sessions.setdefault(key, BrowserSession(key))

    def drop(self, key: str) -> None:
        self._sessions.pop(key, None)

    async def close(self, key: str) -> None:
        async with self._lock:
            session = self._sessions.pop(key, None)
        if session is not None:
            await session.close()

    async def close_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await session.close()


manager = SessionManager()
