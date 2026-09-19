"""``task_runs`` 表的 CRUD 行为（design 027 §2.2 / stage 1）。"""

from __future__ import annotations


def _init_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "runs.db"))
    from app import db

    db.init_db()
    return None


def test_create_run_inserts_pending_row(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )

    run = db.create_run(task["id"])
    assert run["status"] == "pending"
    assert run["output"] == ""
    assert run["error"] == ""
    assert run["delivery_status"] == {}
    assert run["started_at"] is not None
    assert run["finished_at"] is None


def test_update_run_records_progress_and_normalizes_delivery(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )

    run = db.create_run(task["id"])
    db.update_run(run["id"], status="running")
    db.update_run(
        run["id"],
        status="succeeded",
        output="推送成功",
        delivery_status_json={
            "feishu": {"ok": True, "status_code": 200},
            "wecom": {"ok": False, "error": "timeout"},
        },
        finished_at="2026-09-19T10:00:00+00:00",
    )
    final = db.get_run(run["id"])
    assert final["status"] == "succeeded"
    assert final["output"] == "推送成功"
    assert final["finished_at"] == "2026-09-19T10:00:00+00:00"
    assert final["delivery_status"]["feishu"]["ok"] is True
    assert final["delivery_status"]["wecom"]["ok"] is False


def test_update_run_with_no_fields_is_noop(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )
    run = db.create_run(task["id"])
    # 不抛错，且原 status 不变
    after = db.update_run(run["id"])  # 没传字段
    assert after["status"] == "pending"


def test_list_runs_for_task_orders_by_started_at_desc(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )

    r1 = db.create_run(task["id"])
    r2 = db.create_run(task["id"])
    runs = db.list_runs_for_task(task["id"])
    assert [r["id"] for r in runs] == [r2["id"], r1["id"]]


def test_delete_task_cascades_to_task_runs(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )
    run = db.create_run(task["id"])

    db.delete_scheduled_task(task["id"])
    assert db.get_run(run["id"]) is None


def test_scheduled_task_decodes_delivery_and_interactive_json(monkeypatch, tmp_path):
    """``get_scheduled_task`` 把 JSON 列解码出来，避免上游到处 json.loads。"""
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t",
        session_id=session["id"],
        task_type="webhook",
        prompt="近 24h AI 新闻",
        model_id="deepseek/deepseek-chat",
        delivery={
            "channels": [
                {"type": "feishu", "webhook_url": "https://x"}
            ]
        },
        interactive={"notification_title": "执行吗？"},
        allow_full_access=True,
    )

    fetched = db.get_scheduled_task(task["id"])
    assert fetched["prompt"] == "近 24h AI 新闻"
    assert fetched["model_id"] == "deepseek/deepseek-chat"
    assert fetched["allow_full_access"] is True
    assert fetched["delivery_json"]["channels"][0]["type"] == "feishu"
    assert fetched["interactive_json"]["notification_title"] == "执行吗？"


def test_update_scheduled_task_with_prompt_and_delivery(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app import db

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )

    # ``update_scheduled_task`` 接列名（**fields 按列匹配）；
    # schema 字段 ``delivery`` → ``delivery_json`` 的翻译在 api/scheduled_tasks.py。
    updated = db.update_scheduled_task(
        task["id"],
        prompt="新提示词",
        allow_full_access=True,
        delivery_json={"channels": [{"type": "wecom"}]},
    )
    assert updated["prompt"] == "新提示词"
    assert updated["allow_full_access"] is True
    assert updated["delivery_json"]["channels"][0]["type"] == "wecom"