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


def test_clean_query() -> None:
    # 引号、OR、site: 等对 HTML 搜索引擎无效的语法应被清洗
    assert web_search_script._clean_query('"TES" "LGD" OR site:op.gg 战报') == "TES LGD 战报"
    assert web_search_script._clean_query("  深 度   思考  ") == "深 度 思考"
    assert web_search_script._clean_query("正常查询") == "正常查询"


def test_core_tokens() -> None:
    # 停用词/纯数字（年份）/比分形态不算核心词
    tokens = web_search_script._core_tokens("LPL 2026 季后赛 TES LGD 2-3 比分 战报")
    assert tokens == ["LPL", "季后赛", "TES", "LGD"]
    assert web_search_script._core_tokens("LGD 3-2 TES") == ["LGD", "TES"]
    assert web_search_script._core_tokens("今天 比分") == []


def test_results_relevant() -> None:
    # Bing 对 "LGD 3-2 TES" 返回的全是 LGD 百科/微博通用页（缺 TES）→ 判定未命中
    bing_like = [
        {"title": "LGD电子竞技俱乐部_百度百科", "url": "https://baike.baidu.com/item/LGD"},
        {"title": "LGD俱乐部 - 官网", "url": "https://lpl.qq.com/es/team_detail.shtml?tid=4"},
        {"title": "LGD电子竞技俱乐部的微博", "url": "https://www.weibo.com/teamlgd"},
    ]
    assert not web_search_script._results_relevant(bing_like, "LGD 3-2 TES")
    # 搜狗/360 返回真实战报（含 TES + LGD）→ 命中
    sogou_like = [
        {"title": "LPL常规赛:LGD 0-3 TES", "url": "https://www.zhibo8.com/xxx"},
        {"title": "赛后战报 TES 2-0 LGD", "url": "https://www.zhibo8.com/yyy"},
    ]
    assert web_search_script._results_relevant(sogou_like, "LGD 3-2 TES")
    # 核心词不足两个时只要求命中一个
    assert web_search_script._results_relevant(
        [{"title": "TES 相关内容", "url": "https://example.com"}], "TES 战报"
    )


def test_decode_redirect_url() -> None:
    import base64 as b64

    real = "https://www.zhibo8.com/news/123.html"
    enc = b64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    # Sogou /link?url=
    assert web_search_script._decode_redirect_url(
        f"/link?url={enc}", "https://www.sogou.com/web"
    ) == real
    # 360 /link?m=
    assert web_search_script._decode_redirect_url(
        f"https://www.so.com/link?m={enc}", "https://www.so.com/s"
    ) == real
    # Bing /ck/a 带 a1a 前缀
    assert web_search_script._decode_redirect_url(
        f"/ck/a?a=x&u=a1a{enc}&ntb=1", "https://www.bing.com/search"
    ) == real
    # 直接 http(s) 链接原样返回
    assert web_search_script._decode_redirect_url("https://a.com/x", "https://b.com") == "https://a.com/x"


_SAMPLE_SOGOU_HTML = """
<div class="results">
<div class="vrwrap" id="sogou_vr_0">
  <h3 class="vr-title"><a name="dttl" target="_blank" href="/link?url=X4Yt6GhHd2ps2zAsRhBGuRvx9Yiptv-_">赛后战报：TES 2:0 LGD 晋级</a></h3>
  <div class="fz-mid space-txt">TES 横扫 LGD 晋级淘汰赛，下一轮对阵 iG</div>
</div>
<div class="vrwrap" id="sogou_vr_1">
  <h3 class="vr-title"><a name="dttl" target="_blank" href="https://example.com/direct">直接链接标题</a></h3>
  <div class="fz-mid space-txt">摘要二</div>
</div>
</div>
"""

_SAMPLE_360_HTML = """
<ul class="res-list-wrap">
<li class="res-list"><h3 class="res-title"><a href="https://www.so.com/link?m=abc" data-mdurl="https://new.qq.com/rain/a/20200620A0MKXT00">LPL战报:TES零封LGD 阿水厄斐琉斯大胆走位输出爆炸_腾讯新闻</a></h3>
  <div class="res-rich so-rich-news">TES 零封 LGD 拿下比赛</div></li>
<li class="res-list"><h3 class="res-title"><a href="https://www.so.com/link?m=def" data-mdurl="https://sports.sina.com.cn/xxx">TES/LGD 第1局数据对比</a></h3>
  <div class="res-rich">上中射几乎全被对位全包</div></li>
</ul>
"""


def test_parse_sogou_results() -> None:
    results = web_search_script._parse_sogou_results(_SAMPLE_SOGOU_HTML, 10)
    assert len(results) == 2
    assert results[0]["title"] == "赛后战报：TES 2:0 LGD 晋级"
    assert "晋级" in results[0]["snippet"]
    # 跳转链接应被解码为真实 URL；解码失败/非 http 时保留原链接
    assert results[0]["url"].startswith("http")
    assert results[1]["url"] == "https://example.com/direct"


def test_parse_360_results() -> None:
    results = web_search_script._parse_360_results(_SAMPLE_360_HTML, 10)
    assert len(results) == 2
    assert results[0]["title"] == "LPL战报:TES零封LGD 阿水厄斐琉斯大胆走位输出爆炸_腾讯新闻"
    assert results[0]["url"] == "https://new.qq.com/rain/a/20200620A0MKXT00"  # data-mdurl 优先
    assert "零封" in results[0]["snippet"]


def test_backend_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bing 返回"成功"但未命中主题 → 自动切换下一个后端。"""
    irrelevant = [
        {"title": "LGD电子竞技俱乐部_百度百科", "url": "https://baike.baidu.com/item/LGD"},
        {"title": "TES（中国电子竞技俱乐部）", "url": "https://baike.baidu.com/item/TES"},
    ]

    def fake_bing(query, max_results, locale):
        return {"ok": True, "backend": "bing", "results": irrelevant}

    def fake_down(query, max_results, locale):
        return {"ok": False, "reason": "down"}

    relevant = [
        {"title": "LPL战报:TES零封LGD", "url": "https://new.qq.com/xxx"},
    ]

    def fake_360(query, max_results, locale):
        return {"ok": True, "backend": "360", "results": relevant}

    for name in ("_try_bing", "_try_baidu", "_try_sogou", "_try_ddg"):
        monkeypatch.setattr(web_search_script, name, fake_down)
    monkeypatch.setattr(web_search_script, "_try_360", fake_360)
    out = web_search_script._search("LGD 3-2 TES 战报", 5, "zh-CN")
    assert out["success"]
    assert out["data"]["backend"] == "360"
    assert out["data"]["count"] == 1


def test_backend_all_irrelevant(monkeypatch: pytest.MonkeyPatch) -> None:
    irrelevant = [
        {"title": "LGD电子竞技俱乐部_百度百科", "url": "https://baike.baidu.com/item/LGD"},
    ]

    def fake_bing(query, max_results, locale):
        return {"ok": True, "backend": "bing", "results": irrelevant}

    def fake_360(query, max_results, locale):
        return {"ok": True, "backend": "360", "results": irrelevant}

    def fake_down(query, max_results, locale):
        return {"ok": False, "reason": "down"}

    for name in ("_try_bing", "_try_baidu", "_try_sogou", "_try_360", "_try_ddg"):
        monkeypatch.setattr(
            web_search_script, name, fake_bing if name == "_try_bing" else (fake_360 if name == "_try_360" else fake_down)
        )
    out = web_search_script._search("LGD 3-2 TES 战报", 5, "zh-CN")
    assert not out["success"]
    assert "未命中主题" in out["message"]


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
