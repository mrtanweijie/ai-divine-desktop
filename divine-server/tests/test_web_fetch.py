"""Tests for the web_fetch tool (双层策略：静态直连 + 浏览器兜底)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.tools.adapters.web_fetch import WebFetchAdapter
from app.tools.registry import get_tool

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts"
)
SCRIPT = SCRIPTS_DIR / "web_fetch.py"

# web_fetch.py 顶层 import web_common（同目录兄弟模块），需把 scripts 目录加进 sys.path
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("web_fetch_script", SCRIPT)
assert spec and spec.loader
web_fetch_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_fetch_script)

import web_common  # noqa: E402


def test_adapter_registered() -> None:
    adapter = get_tool("web_fetch")
    assert adapter is not None
    assert adapter.name == "web_fetch"
    assert adapter.script_name == "web_fetch.py"
    assert adapter.category == "web"
    assert adapter.timeout >= 60
    assert isinstance(adapter, WebFetchAdapter)


def test_build_params() -> None:
    adapter = WebFetchAdapter(name="web_fetch", description="", parameters={})
    assert adapter.build_params({}) == {"url": ""}
    assert adapter.build_params({"url": "https://a.com"}) == {"url": "https://a.com"}
    out = adapter.build_params(
        {
            "url": "https://a.com",
            "wait_selector": "tbody tr",
            "api_fragment": "/api/list",
        }
    )
    assert out == {
        "url": "https://a.com",
        "wait_selector": "tbody tr",
        "api_fragment": "/api/list",
    }
    # 空串提示参数不应进入 params
    out2 = adapter.build_params(
        {"url": "https://a.com", "wait_selector": "", "api_fragment": ""}
    )
    assert out2 == {"url": "https://a.com"}


def test_text_content_json_pretty() -> None:
    content = web_common.text_content(
        '{"a":1,"b":[1,2]}', "application/json; charset=utf-8"
    )
    assert json.loads(content) == {"a": 1, "b": [1, 2]}


def test_text_content_html() -> None:
    html = (
        "<html><head><title>标题</title></head><body>"
        "<p>正文内容</p><script>var x=1;</script></body></html>"
    )
    content = web_common.text_content(html, "text/html; charset=utf-8")
    assert "标题" in content
    assert "正文内容" in content
    assert "var x=1" not in content


def test_is_sparse() -> None:
    # JS 渲染空壳：可见正文为空，只有脚本与空容器
    shell = (
        "<html><head><title>Loading</title></head><body>"
        "<script src='/app.js'></script><div id='root'></div></body></html>"
    )
    assert web_common.is_sparse(shell, "text/html")
    # 纯重定向壳页
    redirect_shell = (
        "<html><head><title>Redirecting to: /en-US</title></head>"
        "<body>Redirecting to: /en-US</body></html>"
    )
    assert web_common.is_sparse(redirect_shell, "text/html")
    # 真实内容页
    full = "<html><body><p>" + "内容" * 100 + "</p></body></html>"
    assert not web_common.is_sparse(full, "text/html")
    # JSON 响应不触发空壳检测
    assert not web_common.is_sparse('{"a":1}', "application/json")


def test_is_sparse_spa_shell() -> None:
    # SPA 壳：Next.js 挂载点 + 大量导航文本（如 OP.GG），正文异步加载 → 应判为壳
    nav = "\n".join(["游戏", "云顶之弈", "无畏契约", "绝地求生", "登录"] * 20)
    opgg_shell = (
        "<html><head><title>LPL赛程、排名和结果 | OP.GG电竞</title></head>"
        f"<body><div id='__next'><nav>{nav}</nav><main></main></div>"
        "<script src='/_next/static/chunks/main.js'></script></body></html>"
    )
    assert web_common.is_sparse(opgg_shell, "text/html")
    # 无挂载点的静态导航页（非 SPA）不应误判
    static_nav = "<html><body><nav>" + nav + "</nav></body></html>"
    assert not web_common.is_sparse(static_nav, "text/html")
    # Next.js 但正文足够长（服务端渲染的文章页）不应误判
    article = (
        "<html><body><div id='__next'><article>"
        + "正文段落内容" * 500
        + "</article></div></body></html>"
    )
    assert not web_common.is_sparse(article, "text/html")


def test_browser_fallback_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_common, "BROWSER_AVAILABLE", False)
    method, payload = web_common.browser_fallback("https://example.com", {})
    assert method is None
    assert "DrissionPage" in str(payload)


def test_is_local_url() -> None:
    assert web_common.is_local_url("http://127.0.0.1:8000/x")
    assert web_common.is_local_url("http://localhost/x")
    assert web_common.is_local_url("http://192.168.1.1/x")
    assert not web_common.is_local_url("https://example.com/x")


def test_live_static_fetch_smoke() -> None:
    """End-to-end via subprocess（静态路径）；网络不可用时跳过。"""
    payload = {
        "workspace": str(Path.cwd()),
        "output_dir": str(Path.cwd() / "out"),
        "params": {"url": "https://example.com"},
        "locale": "zh-CN",
    }
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    out = json.loads(completed.stdout)
    if not out["success"]:
        pytest.skip(f"网络不可用: {out.get('message')}")
    assert out["data"]["method"] == "static"
    assert "Example Domain" in out["content"]
