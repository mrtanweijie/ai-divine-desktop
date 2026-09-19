"""``webhook`` 任务 handler（design 027 §3.3）。

Agent 执行用桩替代（不真跑 LLM），投递用 httpx.MockTransport 截获。
"""

from __future__ import annotations

import asyncio
import json

import httpx

from app.agent.tasks import delivery


def _init_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "wh.db"))
    from app import db

    db.init_db()
    return db


def _install_channel(monkeypatch, status: int = 200):
    """注册一个走 MockTransport 的 feishu 通道，返回 captured。"""
    from app.agent.tasks.channels import FeishuChannel

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(status, json={"code": 0})

    monkeypatch.setattr(
        delivery,
        "_REGISTRY",
        {"feishu": FeishuChannel(transport=httpx.MockTransport(handler))},
    )
    return captured


def _make_task(db, tmp_path, **overrides):
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    defaults = dict(
        title="每日热点",
        session_id=session["id"],
        task_type="webhook",
        prompt="收集近 24h AI 新闻",
        delivery={"channels": [{"type": "feishu", "webhook_url": "https://f/h"}]},
    )
    defaults.update(overrides)
    return db.create_scheduled_task(**defaults)


def test_webhook_runs_agent_and_delivers_final_answer(monkeypatch, tmp_path):
    import app.agent.tasks.webhook as wh

    db = _init_env(monkeypatch, tmp_path)
    captured = _install_channel(monkeypatch)

    async def fake_agent(task):
        assert task["prompt"] == "收集近 24h AI 新闻", "提示词没透传到 Agent"
        return [
            {"role": "user", "content": "收集近 24h AI 新闻"},
            {"role": "assistant", "content": "我先查一下"},
            {"role": "tool", "content": "tool result"},
            {"role": "assistant", "content": "最终答案：AI 热点三条"},
        ]

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    asyncio.run(wh.run_webhook_task(task))

    runs = db.list_runs_for_task(task["id"])
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "succeeded"
    # 取最后一条 assistant，中间步骤不投递
    assert run["output"] == "最终答案：AI 热点三条"
    assert run["delivery_status"]["feishu"]["ok"] is True
    assert captured["body"]["card"]["elements"][0]["content"] == (
        "最终答案：AI 热点三条"
    )


def test_webhook_marks_failed_when_all_channels_fail(monkeypatch, tmp_path):
    import app.agent.tasks.webhook as wh

    db = _init_env(monkeypatch, tmp_path)
    _install_channel(monkeypatch, status=500)

    async def fake_agent(task):
        return [{"role": "assistant", "content": "答案"}]

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    asyncio.run(wh.run_webhook_task(task))

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "failed"
    assert "feishu" in (run["error"] or "")
    assert run["delivery_status"]["feishu"]["ok"] is False


def test_webhook_succeeds_without_channels(monkeypatch, tmp_path):
    """没配频道 = 只跑不投；执行本身成功就该标 succeeded。"""
    import app.agent.tasks.webhook as wh

    db = _init_env(monkeypatch, tmp_path)

    async def fake_agent(task):
        return [{"role": "assistant", "content": "只跑不投"}]

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path, delivery={"channels": []})

    asyncio.run(wh.run_webhook_task(task))

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "succeeded"
    assert run["output"] == "只跑不投"
    assert run["delivery_status"] == {}


def test_webhook_catches_agent_exception(monkeypatch, tmp_path):
    import app.agent.tasks.webhook as wh

    db = _init_env(monkeypatch, tmp_path)
    _install_channel(monkeypatch)

    async def boom(task):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", boom)
    task = _make_task(db, tmp_path)

    asyncio.run(wh.run_webhook_task(task))  # 不抛

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "failed"
    assert "agent exploded" in (run["error"] or "")


def test_webhook_unknown_channel_records_error(monkeypatch, tmp_path):
    import app.agent.tasks.webhook as wh

    db = _init_env(monkeypatch, tmp_path)
    monkeypatch.setattr(delivery, "_REGISTRY", {})

    async def fake_agent(task):
        return [{"role": "assistant", "content": "答案"}]

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    asyncio.run(wh.run_webhook_task(task))

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "failed"
    assert "unknown channel" in (run["error"] or "")
