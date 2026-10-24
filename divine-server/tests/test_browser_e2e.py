"""browser_engine 端到端测试：真实 Chrome + 本地 fixture 页面。

需要本机存在 Chrome/Chromium/Edge（不下载 playwright 内核——引擎本就设计为
attach 用户已有浏览器）。找不到浏览器时整体跳过。
覆盖（031 §4/§6.1/§14.3）：
- navigate/snapshot：ref 标注与快照文本；
- irreversible 点击在 confirmed=false 委派段被拒绝，confirmed=true 放行；
- 凭据字段输入无条件拒绝；
- 变更操作自动带新快照；
- 购物域策略钩子（金额护栏）附着在快照/抽取结果上。
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import random
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from app.tools.browser_engine import engine, policy
from app.tools.browser_engine.session import manager

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

pytestmark = pytest.mark.skipif(
    not any(Path(p).exists() for p in _CHROME_CANDIDATES),
    reason="本机无 Chrome/Chromium/Edge，跳过浏览器端到端测试",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_cdp(url: str, timeout: float = 15.0) -> bool:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/json/version", timeout=1.5).status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return False


@pytest.fixture()
def chrome_cdp(monkeypatch):
    binary = next(Path(p) for p in _CHROME_CANDIDATES if Path(p).exists())
    port = random.randint(20000, 60000)  # noqa: S311
    profile = tempfile.mkdtemp(prefix="divine-browser-test-")
    process = subprocess.Popen(  # noqa: S603
        [
            str(binary),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--headless=new",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    if not _wait_cdp(url):
        process.terminate()
        pytest.fail("测试 Chrome 调试端口启动超时")
    monkeypatch.setenv("DIVINE_BROWSER_CDP_ENDPOINT", url)

    server_dir = Path(__file__).parent / "fixtures"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(server_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port_http = httpd.server_address[1]

    import threading

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield url, f"http://127.0.0.1:{port_http}/browser_task_page.html"

    # 注意：不在这里关闭 browser session——playwright 对象绑定在测试自己的
    # asyncio.run 循环上，跨循环关闭会死锁；由各测试在 finally 里自清。
    httpd.shutdown()
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture()
def shopping_domain(monkeypatch):
    """把购物域命中规则指向本地 fixture 域名，验证策略钩子附着。"""
    monkeypatch.setattr(policy, "shopping_domains", lambda: ("127.0.0.1",))
    monkeypatch.setattr(policy, "per_order_cap", lambda: 200.0)


def _ref_by_name(session: Any, keyword: str) -> str | None:
    for ref, meta in session.refs.items():
        if keyword in (meta.get("name") or ""):
            return ref
    return None


def test_browser_engine_end_to_end(chrome_cdp, shopping_domain, tmp_path):
    _, page_url = chrome_cdp
    session = manager.get("test-session")

    async def run() -> None:
        # 1. 导航 → 快照：标题/ref 齐全，策略钩子附带金额护栏
        result = await engine.op_navigate(session, tmp_path, page_url)
        assert result["success"], result
        assert "测试商店" in result["snapshot"]
        assert result["policy"]["domain_pack"] == "shopping"
        assert result["policy"]["amount_guard"]["verdict"] == "block"

        # 2. irreversible 点击被拒（confirmed=false 委派段）
        submit_ref = _ref_by_name(session, "提交订单")
        assert submit_ref
        refused = await engine.op_click(session, tmp_path, submit_ref)
        assert refused["success"] is False
        assert refused["rejected"] is True
        assert refused["risk"] == "irreversible"

        # 3. 凭据输入无条件拒绝
        pw_ref = _ref_by_name(session, "支付密码")
        assert pw_ref
        cred_refused = await engine.op_fill(session, tmp_path, pw_ref, "123456")
        assert cred_refused["success"] is False
        assert cred_refused["rejected"] is True
        assert cred_refused["risk"] == "credential"

        # 4. confirmed=true 后 irreversible 放行，且返回新快照
        session.confirmed = True
        try:
            clicked = await engine.op_click(session, tmp_path, submit_ref)
            assert clicked["success"], clicked
        finally:
            session.confirmed = False

        # 5. 可逆变更：fill/select 正常并带新快照
        kw_ref = _ref_by_name(session, "搜索商品")
        assert kw_ref
        filled = await engine.op_fill(session, tmp_path, kw_ref, "生椰拿铁")
        assert filled["success"]
        assert "生椰拿铁" in filled["snapshot"]

        spec_ref = _ref_by_name(session, "规格")
        if spec_ref:
            selected = await engine.op_select(session, tmp_path, spec_ref, "大杯")
            assert selected["success"]

        # 6. extract：结构化抽取 + 策略附着
        extracted = await engine.op_extract(
            session, tmp_path, selectors={"totals": ".total", "links": "a"}
        )
        assert extracted["success"]
        assert "¥258.00" in " ".join(extracted["data"]["totals"])
        assert extracted["policy"]["amount_guard"]["amount"] == 258.0

        # 7. 掘金式场景：无 role 的 cursor:pointer 控件与 contenteditable 编辑器可寻址
        picker_ref = next(
            (r for r, m in session.refs.items()
             if m.get("role") == "clickable" and "请选择圈子" in (m.get("name") or "")),
            None,
        )
        assert picker_ref, f"cursor:pointer 控件未进快照: {session.refs}"
        picked = await engine.op_click(session, tmp_path, picker_ref)
        assert picked["success"], picked

        editor_ref = next(
            (r for r, m in session.refs.items()
             if m.get("role") == "textbox" and not (m.get("name") or "").strip()),
            None,
        )
        assert editor_ref, "contenteditable 编辑器未以 textbox 进快照"
        filled_rich = await engine.op_fill(session, tmp_path, editor_ref, "通用引擎实测富文本")
        assert filled_rich["success"], filled_rich
        assert "通用引擎实测富文本" in filled_rich["snapshot"]

        pressed = await engine.op_press_key(session, tmp_path, "Enter", ref=editor_ref)
        assert pressed["success"], pressed

        # 8. ref 过期检测：编造 ref 返回过期错误而非异常
        stale = await engine.op_click(session, tmp_path, "e999999")
        assert stale["success"] is False
        assert "过期" in stale["message"] or "不存在" in stale["message"]

    async def guarded() -> None:
        try:
            await run()
        finally:
            await manager.close_all()  # 与 ops 同一循环内关闭，避免跨循环死锁

    asyncio.run(guarded())


def test_navigate_rejects_non_http(chrome_cdp, tmp_path):
    session = manager.get("test-session-scheme")

    async def run() -> None:
        try:
            result = await engine.op_navigate(session, tmp_path, "file:///etc/passwd")
            assert result["success"] is False
            assert result["rejected"] is True
        finally:
            await manager.close_all()

    asyncio.run(run())
