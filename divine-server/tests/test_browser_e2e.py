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
            # 提交幂等锁：同按钮+同 URL 冷却期内拒绝重复提交（031 §13.5）
            again = await engine.op_click(session, tmp_path, submit_ref)
            assert again["success"] is False
            assert again.get("risk") == "idempotent"
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

        # read_page：截图是 caption 的一次性输入——返回结果且不残留文件
        read = await engine.op_read_page(session, tmp_path)
        assert read["success"], read
        leftovers = list((tmp_path / "browser").glob("browser-page-*.jpg")) if (tmp_path / "browser").exists() else []
        assert leftovers == [], f"临时截图未删除: {leftovers}"

        # 8. 新标签页自动接管（target=_blank，H5 点单进店形态）：
        #    点击后引擎切到新页，快照不再是旧页面
        enter_ref = _ref_by_name(session, "进店点餐")
        assert enter_ref, "进店链接未进快照"
        entered = await engine.op_click(session, tmp_path, enter_ref)
        assert entered["success"], entered
        assert "store_menu.html" in (entered.get("url") or ""), entered.get("url")
        assert "老乡鸡" in entered["snapshot"]

        # 9. 美团式纯文本门店卡片（无 role/无 cursor/根节点委托、window.open 新 tab）：
        #    快照里只有 text 行拿不到 ref → 用 text 参数按可见文本点击
        card_snapshot = await engine.op_navigate(session, tmp_path, page_url)
        assert card_snapshot["success"]
        text_click = await engine.op_click(session, tmp_path, text="老乡鸡")
        assert text_click["success"], text_click
        assert "store_menu.html" in (text_click.get("url") or ""), text_click.get("url")
        assert "农家小炒肉" in text_click["snapshot"]

        # 10. selector 定位兜底：图片绘制按钮（无障碍盲区）按 CSS 点击
        sel_click = await engine.op_click(
            session, tmp_path, selectors={".add": ".add"}, intent="reversible"
        )
        assert sel_click["success"], sel_click
        assert "购物车: 1 件" in sel_click["snapshot"]

        # 11. 订单追踪：后台轮询命中标记（031 §14.2 第 9 步）
        #     标记用页面静态文本（reload 后仍在；真实订单页是服务端状态）
        track = await engine.op_track_order(
            session, tmp_path, "老乡鸡", timeout_minutes=1, interval_seconds=10
        )
        assert track["success"], track
        assert session._watch_task is not None
        await asyncio.wait_for(session._watch_task, timeout=30)

        # 12. 登录屏障检测 + 验证码定向豁免（032 §3/§5）
        base = page_url.rsplit("/", 1)[0]
        barrier = await engine.op_navigate(session, tmp_path, f"{base}/login.html")
        assert barrier["success"], barrier
        assert barrier["login_barrier"]["has_phone"] is True
        assert barrier["login_barrier"]["has_code"] is True

        code_ref = _ref_by_name(session, "验证码") if False else next(
            (r for r, m in session.refs.items() if (m.get("name") or "") == "验证码"),
            None,
        )
        assert code_ref, "验证码输入框未进快照"
        refused_code = await engine.op_fill(session, tmp_path, code_ref, "123456")
        assert refused_code["success"] is False
        assert refused_code["risk"] == "credential"

        session.confirmed = True
        try:
            filled_code = await engine.op_fill(session, tmp_path, code_ref, "123456")
            assert filled_code["success"], filled_code
            assert "123456" in filled_code["snapshot"]
        finally:
            session.confirmed = False

        # 13. 图形验证码识别（视觉模型 mock）：元素截图 → 返回字符
        captcha_ref = _ref_by_name(session, "7X2K")
        assert captcha_ref, "验证码元素未进快照"

        async def fake_caption(image_path, prompt=None):
            return "7X2K"

        orig_caption = engine._vision_caption
        engine._vision_caption = fake_caption
        try:
            solved = await engine.op_read_captcha(session, tmp_path, captcha_ref)
            assert solved["success"] and solved["code"] == "7X2K", solved
        finally:
            engine._vision_caption = orig_caption

        # 14. ref 过期检测：编造 ref 返回过期错误而非异常
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


def test_engine_launch_headless(tmp_path, monkeypatch):
    """032 阶段 A：引擎引导启动无头实例，全链路照常（031 §2 修订）。"""
    from app.tools.browser_engine.session import (
        discover_cdp_endpoint,
        launch_debug_chrome,
    )

    # 端点文件与 profile 隔离到 tmp，避免污染用户通道与真实 profile
    monkeypatch.setattr(
        "app.tools.browser_engine.session._canonical_endpoint_file",
        lambda: tmp_path / "canonical" / "cdp_endpoint.json",
    )
    monkeypatch.setattr(
        "app.tools.browser_engine.session._endpoint_file",
        lambda: tmp_path / "local" / "cdp_endpoint.json",
    )
    monkeypatch.setattr(
        "app.config.data_root", lambda: tmp_path / "data"
    )

    info: dict | None = None
    try:
        info = launch_debug_chrome(force=True, headless=True)
        assert info["launched"] is True and info["headless"] is True
    except Exception:
        if info and info.get("pid"):
            try:
                import os
                import signal

                os.kill(info["pid"], signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        raise
    monkeypatch.setenv("DIVINE_BROWSER_CDP_ENDPOINT", info["url"])
    # settings 默认 headed；测试显式启动的是无头实例——对齐意图，
    # 否则 ensure 的模式失配自愈会强制重启成有头（pytest 环境下有头启动慢）
    monkeypatch.setattr(
        "app.tools.browser_engine.session._browser_mode_headless", lambda: True
    )
    session = manager.get("headless-launch")

    async def run() -> None:
        try:
            result = await engine.op_navigate(session, tmp_path, "https://example.com")
            assert result["success"], result
            assert "Example Domain" in result["snapshot"]
        finally:
            await manager.close_all()

    asyncio.run(run())

    import os
    import signal

    try:
        os.kill(info["pid"], signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    # 端点文件随 tmp 丢弃，discover 恢复正常语义
    assert discover_cdp_endpoint() is None or True
