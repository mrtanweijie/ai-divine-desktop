"""``digest`` 任务类型（design 027 §3.5）：来源抓取 + 模板填充 + 投递。"""

from __future__ import annotations

import asyncio
import json

import httpx

from app.agent.tasks import delivery
from app.agent.tasks.digest import (
    fetch_url,
    fill_template,
    gather_sources,
    run_digest_task,
)


def _init_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "dg.db"))
    from app import db

    db.init_db()
    return db


def _install_channel(monkeypatch):
    from app.agent.tasks.channels import FeishuChannel

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0})

    monkeypatch.setattr(
        delivery,
        "_REGISTRY",
        {"feishu": FeishuChannel(transport=httpx.MockTransport(handler))},
    )
    return captured


# --------------------------------------------------------------- 模板填充


def test_fill_template_replaces_placeholder():
    gathered = [{"name": "a.md", "content": "内容 A"}]
    out = fill_template("总结：\n{sources}", gathered)
    assert out == "总结：\n### a.md\n内容 A"


def test_fill_template_appends_when_no_placeholder():
    gathered = [{"name": "b.md", "content": "内容 B"}]
    out = fill_template("请总结", gathered)
    assert out.startswith("请总结")
    assert "内容 B" in out


def test_fill_template_empty_gathered_returns_prompt():
    assert fill_template("提示词", []) == "提示词"


def test_fill_template_empty_prompt_returns_blocks():
    gathered = [{"name": "c.md", "content": "内容 C"}]
    assert fill_template("", gathered) == "### c.md\n内容 C"


def test_fill_template_multiple_sources():
    gathered = [
        {"name": "a", "content": "A"},
        {"name": "b", "content": "B"},
    ]
    out = fill_template("{sources}", gathered)
    assert "### a\nA" in out and "### b\nB" in out


# --------------------------------------------------------------- 来源抓取


def test_gather_sources_reads_local_file(tmp_path):
    source = tmp_path / "news.md"
    source.write_text("今日要闻", encoding="utf-8")
    out = asyncio.run(gather_sources([str(source)], tmp_path))
    assert out == [{"name": "news.md", "content": "今日要闻"}]


def test_gather_sources_accepts_dict_form(tmp_path):
    source = tmp_path / "x.txt"
    source.write_text("内容", encoding="utf-8")
    out = asyncio.run(gather_sources([{"path": str(source)}], tmp_path))
    assert out[0]["content"] == "内容"


def test_gather_sources_bad_target_is_not_fatal(tmp_path):
    out = asyncio.run(gather_sources(["不是路径也不是URL"], tmp_path))
    assert out[0]["name"] == "不是路径也不是URL"
    assert "无法识别" in out[0]["content"]


def test_gather_sources_skips_empty(tmp_path):
    assert asyncio.run(gather_sources(["", None, {}], tmp_path)) == []


def test_fetch_url_uses_web_fetch_tool(monkeypatch, tmp_path):
    """复用现有 web_fetch 适配器 —— 传 url 进去，取 content 出来。"""
    calls: list[dict] = []

    class _FakeResult:
        success = True
        message = "ok"
        content = "网页正文"

    class _FakeAdapter:
        async def run(self, workspace, arguments):
            calls.append({"workspace": str(workspace), **arguments})
            return _FakeResult()

    import app.tools.registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda name: _FakeAdapter())
    out = asyncio.run(fetch_url("https://example.com", tmp_path))
    assert out["content"] == "网页正文"
    assert calls[0]["url"] == "https://example.com"


def test_fetch_url_reports_failure(monkeypatch, tmp_path):
    class _FakeResult:
        success = False
        message = "404 not found"
        content = ""

    class _FakeAdapter:
        async def run(self, workspace, arguments):
            return _FakeResult()

    import app.tools.registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda name: _FakeAdapter())
    out = asyncio.run(fetch_url("https://bad", tmp_path))
    assert "抓取失败" in out["content"]
    assert "404" in out["content"]


def test_fetch_url_when_tool_missing(monkeypatch, tmp_path):
    import app.tools.registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda name: None)
    out = asyncio.run(fetch_url("https://x", tmp_path))
    assert "未注册" in out["content"]


# --------------------------------------------------------------- 端到端


def test_digest_gathers_then_runs_then_delivers(monkeypatch, tmp_path):
    import app.agent.tasks.digest as dg

    db = _init_env(monkeypatch, tmp_path)
    captured = _install_channel(monkeypatch)

    source = tmp_path / "热点.md"
    source.write_text("AI 新闻：模型发布", encoding="utf-8")

    seen: dict = {}

    async def fake_agent(task):
        seen["prompt"] = task["prompt"]
        return [{"role": "assistant", "content": "摘要：模型发布"}]

    monkeypatch.setattr(dg, "run_agent_with_user_prompt", fake_agent)

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="每日热点",
        session_id=session["id"],
        task_type="digest",
        prompt="请把以下内容总结为三条：\n{sources}",
        digest={"sources": [str(source)]},
        delivery={"channels": [{"type": "feishu", "webhook_url": "https://f/h"}]},
    )

    asyncio.run(run_digest_task(task))

    # 来源内容被填进了 prompt，Agent 拿到的是填好的模板
    assert "AI 新闻：模型发布" in seen["prompt"]
    assert "请把以下内容总结为三条" in seen["prompt"]

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "succeeded"
    assert run["output"] == "摘要：模型发布"
    assert run["delivery_status"]["feishu"]["ok"] is True
    assert captured["body"]["card"]["elements"][0]["content"] == "摘要：模型发布"


def test_digest_without_sources_still_runs(monkeypatch, tmp_path):
    import app.agent.tasks.digest as dg

    db = _init_env(monkeypatch, tmp_path)
    _install_channel(monkeypatch)

    async def fake_agent(task):
        return [{"role": "assistant", "content": "无来源摘要"}]

    monkeypatch.setattr(dg, "run_agent_with_user_prompt", fake_agent)
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t",
        session_id=session["id"],
        task_type="digest",
        prompt="随便总结",
        delivery={"channels": [{"type": "feishu", "webhook_url": "https://f/h"}]},
    )

    asyncio.run(run_digest_task(task))
    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "succeeded"
    assert run["output"] == "无来源摘要"


def test_digest_catches_exception(monkeypatch, tmp_path):
    import app.agent.tasks.digest as dg

    db = _init_env(monkeypatch, tmp_path)
    _install_channel(monkeypatch)

    async def boom(task):
        raise RuntimeError("digest exploded")

    monkeypatch.setattr(dg, "run_agent_with_user_prompt", boom)
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="digest", prompt="x"
    )

    asyncio.run(run_digest_task(task))  # 不抛
    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "failed"
    assert "digest exploded" in (run["error"] or "")
