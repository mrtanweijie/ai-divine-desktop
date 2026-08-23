"""Tests for the web_search tool (script parsing + adapter wiring)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.constants import _READ_ONLY_TOOLS
from app.agent.subagents import _SUBAGENT_READ_ONLY_TOOLS
from app.tools.adapters.web_search import WebSearchAdapter
from app.tools.registry import get_tool

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "app" / "tools" / "scripts" / "web_search.py"
)

spec = importlib.util.spec_from_file_location("web_search_script", SCRIPT)
assert spec and spec.loader
web_search_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_search_script)

_SAMPLE_DDG_HTML = """
<html><body>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fapi-docs.deepseek.com%2Fzh-cn%2Fquick_start%2Fpricing%2F&amp;rut=abc123">
    模型 &amp; 价格 | DeepSeek API Docs
  </a>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=...">扣减费用 = token 消耗量 × 模型单价</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/direct">直接链接标题</a>
  <span class="result__snippet">这是一段摘要文本</span>
</div>
<div class="result">
  <span>缺少标题和链接的无效条目</span>
</div>
</body></html>
"""

_SAMPLE_BAIDU_HTML = """
<html><body>
<div class="result c-container xpath-log new-pmd" mu="https://baijiahao.baidu.com/s?id=123&amp;wfr=spider&amp;for=pc">
  <h3 class="t"><a href="http://www.baidu.com/link?url=xxxx">最高涨1100%!<em>DeepSeek</em>新定价今日生效</a></h3>
  <span class="summary-text_15QGa">智东西8月17日报道，今日零时起，DeepSeek正式执行新版API价格</span>
</div>
<div class="result c-container" mu="https://api-docs.deepseek.com/pricing">
  <h3 class="t"><a href="http://www.baidu.com/link?url=yyyy">模型 &amp; 价格 | DeepSeek API Docs</a></h3>
  <div class="c-abstract">扣减费用 = token 消耗量 × 模型单价</div>
</div>
<div class="c-container">
  <h3 class="t"><a href="http://www.baidu.com/link?url=zzzz">无 mu 属性结果</a></h3>
  <span class="summary-text_x">摘要三</span>
</div>
<div class="c-container">
  <span>无标题容器，应被跳过</span>
</div>
</body></html>
"""

_SAMPLE_BING_HTML = """
<html><body>
<ol id="b_results">
<li class="b_algo">
  <h2><a href="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/">模型 &amp; 价格 | DeepSeek API Docs</a></h2>
  <div class="b_caption"><p class="b_lineclamp2">扣减费用 = token 消耗量 × 模型单价</p></div>
</li>
<li class="b_algo">
  <h2><a href="https://www.bing.com/ck/a?a=x&amp;u=a1aaHR0cHM6Ly9wbGF0Zm9ybS5kZWVwc2Vlay5jb20v&amp;ntb=1">DeepSeek Platform</a></h2>
  <div class="b_caption"><p>Join DeepSeek API platform</p></div>
</li>
<li class="b_algo">
  <span>缺少标题链接的条目</span>
</li>
</ol>
</body></html>
"""


def test_adapter_registered() -> None:
    adapter = get_tool("web_search")
    assert adapter is not None
    assert adapter.name == "web_search"
    assert adapter.category == "web"
    assert adapter.script_name == "web_search.py"
    assert isinstance(adapter, WebSearchAdapter)


def test_build_params() -> None:
    adapter = WebSearchAdapter(
        name="web_search", description="", parameters={}
    )
    assert adapter.build_params({}) == {
        "query": "",
        "max_results": 5,
    }
    assert adapter.build_params({"query": "  DeepSeek 价格  ", "max_results": 99}) == {
        "query": "DeepSeek 价格",
        "max_results": 10,
    }
    assert adapter.build_params({"query": "x", "max_results": 0}) == {
        "query": "x",
        "max_results": 1,
    }
    assert adapter.build_params({"query": "x", "max_results": "abc"}) == {
        "query": "x",
        "max_results": 5,
    }


def test_in_tool_sets() -> None:
    assert "web_search" in _READ_ONLY_TOOLS
    assert "web_search" in _SUBAGENT_READ_ONLY_TOOLS


def test_parse_ddg_results() -> None:
    results = web_search_script._parse_ddg_results(_SAMPLE_DDG_HTML, 10)
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "模型 & 价格 | DeepSeek API Docs"
    assert first["url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert "扣减费用" in first["snippet"]
    second = results[1]
    assert second["title"] == "直接链接标题"
    assert second["url"] == "https://example.com/direct"
    assert second["snippet"] == "这是一段摘要文本"


def test_parse_baidu_results() -> None:
    results = web_search_script._parse_baidu_results(_SAMPLE_BAIDU_HTML, 10)
    assert len(results) == 3
    first = results[0]
    assert first["title"] == "最高涨1100%!DeepSeek新定价今日生效"
    assert first["url"] == "https://baijiahao.baidu.com/s?id=123&wfr=spider&for=pc"
    assert "智东西" in first["snippet"]
    second = results[1]
    assert second["title"] == "模型 & 价格 | DeepSeek API Docs"
    assert second["url"] == "https://api-docs.deepseek.com/pricing"
    assert "扣减费用" in second["snippet"]
    # 无 mu 属性时回退到链接 href
    third = results[2]
    assert third["url"] == "http://www.baidu.com/link?url=zzzz"


def test_parse_bing_results() -> None:
    results = web_search_script._parse_bing_results(_SAMPLE_BING_HTML, 10)
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "模型 & 价格 | DeepSeek API Docs"
    assert first["url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert "扣减费用" in first["snippet"]
    # Bing /ck/a 跳转链接的 u 参数（base64url）应被解码为真实 URL
    second = results[1]
    assert second["title"] == "DeepSeek Platform"
    assert second["url"] == "https://platform.deepseek.com/"
    assert second["snippet"] == "Join DeepSeek API platform"


def test_parse_results_caps_count() -> None:
    assert len(web_search_script._parse_bing_results(_SAMPLE_BING_HTML, 1)) == 1
    assert len(web_search_script._parse_ddg_results(_SAMPLE_DDG_HTML, 1)) == 1


def test_live_search_smoke() -> None:
    """End-to-end via subprocess; skipped when the network/backend is down."""
    payload = {
        "workspace": str(Path.cwd()),
        "output_dir": str(Path.cwd() / "out"),
        "params": {"query": "DeepSeek API 价格", "max_results": 3},
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
        pytest.skip(f"搜索后端暂不可用: {out.get('message')}")
    assert out["data"]["count"] >= 1
    assert out["data"]["results"][0]["title"]
    assert out["data"]["results"][0]["url"]
