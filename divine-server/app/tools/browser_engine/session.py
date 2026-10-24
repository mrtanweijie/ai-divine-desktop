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


def _write_endpoint_file(url: str, pid: int | None = None) -> None:
    """端点写入规范位置 + 当前 data_root 副本（尽力而为，失败不阻断）。"""
    payload = json.dumps(
        {"url": url, "ts": time.time(), "pid": pid}, ensure_ascii=False
    )
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


def _kill_stale_instance(profile_dir: Path) -> None:
    """强制重启前清掉旧的专用浏览器实例（可能已半死：端口通但协议无响应）。

    按专用 profile 路径精确匹配命令行，只影响我们启动的实例。
    """
    try:
        subprocess.run(  # noqa: S603 — pkill 固定参数，路径来自配置
            ["pkill", "-f", f"--user-data-dir={profile_dir}"],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)
    except Exception as exc:  # noqa: BLE001 — 清理失败不阻断启动
        logger.warning("清理旧浏览器实例失败: %s", exc)


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
    if force:
        # 同 profile 的旧实例（可能已半死）不清掉，新实例会被它吞掉而拿不到调试端口
        _kill_stale_instance(profile_dir)

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
            _write_endpoint_file(url, process.pid)
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
        # 当前委派段的工具步数（031 §9 步数 cap），委派段开始时归零
        self.steps_this_task = 0
        # 提交幂等锁：最近一次不可逆提交 (url|按钮名, ts)（031 §13.5）
        self.last_submission: tuple[str, float] | None = None

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
        """返回专属 tab 的 Page；两级自愈：端点丢失→引导启动，连接/建页失败→强制重启。

        第 2 级覆盖"端点半死"场景：探测恰好通过、但 CDP 协议交互失败（典型表现
        是 Browser.setDownloadBehavior 协议错误）——此时强制重启专用浏览器再试一次。
        """
        await manager.drain_pending()
        from playwright.async_api import async_playwright

        if self._page is not None:
            try:
                if not self._page.is_closed():
                    return self._page
            except Exception:  # noqa: BLE001
                pass
            self._page = None

        last_error: Exception | None = None
        for attempt in (0, 1):
            try:
                endpoint = discover_cdp_endpoint()
                if endpoint is None:
                    # 自愈：引导启动专用浏览器（专用 profile + 随机端口），端点自动写盘。
                    # 桌面端重启不会恢复独立运行的 Chrome——通道自愈只能靠这里。
                    info = await asyncio.to_thread(launch_debug_chrome)
                    endpoint = info["url"]
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    endpoint, timeout=_CONNECT_TIMEOUT * 1000
                )
                if not self._browser.contexts:
                    raise RuntimeError("浏览器无可上下文（实例状态异常）")
                self._page = await self._browser.contexts[0].new_page()
                self._page.set_default_timeout(_DEFAULT_TIMEOUT_MS)
                return self._page
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — 任何连接/建页失败都走强制重启自愈
                last_error = exc
                logger.warning(
                    "browser connect/page failed (attempt %d/2): %s: %s",
                    attempt + 1,
                    type(exc).__name__,
                    str(exc)[:160],
                )
                await self._close_connection()
                if attempt == 0:
                    await asyncio.to_thread(launch_debug_chrome, True)
        raise RuntimeError(
            "浏览器连接失败（已强制重启专用浏览器仍失败，请关闭该 profile 的所有 "
            f"Chrome 窗口后重试）: {type(last_error).__name__}: {str(last_error)[:200]}"
        ) from last_error

    def page_ids(self) -> set[int]:
        """当前 context 里所有标签页的 id 集合（供动作前后对比发现新 tab）。"""
        if self._browser is not None and self._browser.contexts:
            return {id(p) for p in self._browser.contexts[0].pages}
        return set()

    async def adopt_new_page(self, pages_before: set[int]) -> bool:
        """接管动作新打开的标签页（target=_blank，H5 点单/外链的普遍形态）。

        点击返回时新 tab 可能尚未登记（Chromium 异步开页），因此轮询等待至多
        3s。接管后切换为会话当前页——否则引擎会一直绑在旧 tab 上，快照不变，
        模型陷入无限重试。
        """
        if not (self._browser is not None and self._browser.contexts):
            return False
        deadline = time.monotonic() + 3.0
        new_page: Any = None
        while time.monotonic() < deadline:
            candidates = [
                p
                for p in self._browser.contexts[0].pages
                if id(p) not in pages_before and not p.is_closed()
            ]
            if candidates:
                new_page = candidates[-1]
                break
            await asyncio.sleep(0.15)
        if new_page is None:
            return False
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:  # noqa: BLE001 — 加载慢也先接管，后续 wait 兜底
            pass
        self._page = new_page
        self._page.set_default_timeout(_DEFAULT_TIMEOUT_MS)
        self.refs.clear()  # 新页面，旧 ref 全部作废
        return True

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
        # 会话已删除、待回收的 browser 资源（API 同步路由里标记，事件循环里关闭）
        self._pending_close: set[str] = set()

    def get(self, key: str) -> BrowserSession:
        """同 key 复用；取不到（或之前断开）就新建，失败不缓存。"""
        return self._sessions.setdefault(key, BrowserSession(key))

    def drop(self, key: str) -> None:
        self._sessions.pop(key, None)

    def request_close(self, key: str) -> None:
        """标记待回收：同步上下文（如 API 路由）调用，实际关闭在事件循环里执行。"""
        self._pending_close.add(key)

    async def drain_pending(self) -> None:
        """关闭所有标记回收的会话资源（须在与创建相同的事件循环里调用）。"""
        if not self._pending_close:
            return
        keys = list(self._pending_close)
        self._pending_close.clear()
        for key in keys:
            await self.close(key)

    async def close(self, key: str) -> None:
        async with self._lock:
            session = self._sessions.pop(key, None)
        if session is not None:
            await session.close()

    async def close_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._pending_close.clear()
        for session in sessions:
            await session.close()


manager = SessionManager()
