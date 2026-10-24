"""新机制单测：快照裁剪、步数上限、站点配方、用户域名策略与地址护栏。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.tools import subagents as subagents_mod
from app.agent.tools.subagents import _SUBAGENT_BROWSER_TOOLS
from app.tools.browser_engine import policy, recipes
from app.tools.browser_engine.trim import BrowserSnapshotTrimMiddleware


# ---------------------------------------------------------------------------
# BrowserSnapshotTrimMiddleware — 旧快照替换为占位符，只保留最新一份
# ---------------------------------------------------------------------------


def _make_history() -> list:
    return [
        AIMessage(content="go", tool_calls=[{"id": "c1", "name": "browser_snapshot", "args": {}}]),
        ToolMessage(content="页面: A\nURL: https://a.example\n- button \"x\" [ref=e1]", tool_call_id="c1"),
        AIMessage(content="go on", tool_calls=[{"id": "c2", "name": "browser_snapshot", "args": {}}]),
        ToolMessage(content="页面: B\nURL: https://b.example\n- button \"y\" [ref=e2]", tool_call_id="c2"),
        AIMessage(content="非 browser 工具", tool_calls=[{"id": "c3", "name": "web_search", "args": {}}]),
        ToolMessage(content="搜索结果（不应被裁剪）", tool_call_id="c3"),
    ]


def test_trim_keeps_only_latest_snapshot():
    middleware = BrowserSnapshotTrimMiddleware(_SUBAGENT_BROWSER_TOOLS)
    captured: dict = {}

    async def handler(request):
        captured["messages"] = request.messages
        return "ok"

    import asyncio

    request = SimpleNamespace(messages=_make_history())
    asyncio.run(middleware.awrap_model_call(request, handler))
    msgs = captured["messages"]
    assert "[旧快照已丢弃" in msgs[1].content
    assert "URL: https://a.example" in msgs[1].content  # 占位符保留 URL 行
    assert msgs[3].content.startswith("页面: B")  # 最新一份完整保留
    assert msgs[5].content == "搜索结果（不应被裁剪）"  # 非 browser 工具不受影响


def test_trim_noop_when_single_snapshot():
    middleware = BrowserSnapshotTrimMiddleware(_SUBAGENT_BROWSER_TOOLS)
    history = _make_history()[:2]

    async def handler(request):
        return "ok"

    import asyncio

    asyncio.run(middleware.awrap_model_call(SimpleNamespace(messages=history), handler))
    assert history[1].content.startswith("页面: A")


# ---------------------------------------------------------------------------
# 步数上限判定
# ---------------------------------------------------------------------------


def test_step_cap_message():
    session = SimpleNamespace(steps_this_task=0)
    assert subagents_mod._step_cap_message(session) is None
    session.steps_this_task = subagents_mod.SUBAGENT_BROWSER_STEP_CAP
    message = subagents_mod._step_cap_message(session)
    assert message is not None and "上限" in message


# ---------------------------------------------------------------------------
# 站点配方：加载 / URL 匹配 / 提示块渲染
# ---------------------------------------------------------------------------


def test_recipe_match_and_block(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    recipes_dir = data_dir / "browser" / "recipes"
    recipes_dir.mkdir(parents=True)
    (recipes_dir / "juejin.json").write_text(
        json.dumps(
            {
                "name": "juejin-pins",
                "version": 1,
                "url_patterns": ["*juejin.cn/pin*"],
                "flow_hints": "编辑器为惰性挂载的 contenteditable，先选圈子再快照。",
                "quirks": ["首进有全屏弹窗先关"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (recipes_dir / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(recipes, "recipes_dir", lambda: recipes_dir)

    assert recipes.match_recipes("https://juejin.cn/pin/123") != []
    assert recipes.match_recipes("https://www.oschina.net/") == []
    block = recipes.recipe_block("https://juejin.cn/pin/123")
    assert block is not None
    assert "juejin-pins" in block and "惰性挂载" in block and "弹窗" in block
    assert recipes.recipe_block("https://www.oschina.net/") is None


# ---------------------------------------------------------------------------
# 用户域名策略：禁止名单 / 每次确认名单
# ---------------------------------------------------------------------------


def test_blocked_and_confirm_domains(monkeypatch):
    monkeypatch.setattr(
        policy,
        "_load_settings",
        lambda: {
            "browser_blocked_domains": "evil.com",
            "browser_confirm_domains": "admin.example.com",
        },
    )
    assert policy.blocked_domain_hit("https://evil.com/x") == "evil.com"
    assert policy.blocked_domain_hit("https://good.com/x") is None
    assert policy.in_confirm_domains("https://admin.example.com/y") is True
    assert policy.in_confirm_domains("https://other.com/y") is False


def test_address_guard_warns_on_mismatch(monkeypatch):
    monkeypatch.setattr(policy, "_load_settings", lambda: {"shopping_default_address": "上海市浦东新区世纪大道100号"})
    result = policy.evaluate_shopping_policy(
        "https://item.jd.com/1.html", "收货地址：北京市朝阳区某大厦；应付 ¥16.5"
    )
    assert any("不一致" in w for w in result["warnings"])
    # 一致时不告警
    result2 = policy.evaluate_shopping_policy(
        "https://item.jd.com/1.html", "收货地址：上海市浦东新区世纪大道100号 12F；应付 ¥16.5"
    )
    assert not any("不一致" in w for w in result2["warnings"])
