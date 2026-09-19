"""``GET /scheduled-tasks/{id}/runs``（design 027 §5.4 的执行历史接口）。"""

from __future__ import annotations


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "runs_api.db"))
    from app import db

    db.init_db()
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app), db


def _make_task(db, tmp_path, **overrides):
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    defaults = dict(
        title="t", session_id=session["id"], task_type="webhook", prompt="x"
    )
    defaults.update(overrides)
    return db.create_scheduled_task(**defaults)


def test_list_runs_returns_history(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    task = _make_task(db, tmp_path)
    run = db.create_run(task["id"])
    db.update_run(
        run["id"],
        status="succeeded",
        output="答案",
        delivery_status_json={"feishu": {"ok": True, "status_code": 200}},
    )

    resp = client.get(f"/api/scheduled-tasks/{task['id']}/runs")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["output"] == "答案"
    # delivery_status 已解码成对象，前端可直接用
    assert runs[0]["delivery_status"]["feishu"]["ok"] is True


def test_list_runs_empty_for_legacy_types(monkeypatch, tmp_path):
    """reminder/agent/monitor 不写 task_runs（保持改前行为）。"""
    client, db = _client(monkeypatch, tmp_path)
    task = _make_task(db, tmp_path, task_type="reminder")
    resp = client.get(f"/api/scheduled-tasks/{task['id']}/runs")
    assert resp.status_code == 200
    assert resp.json()["runs"] == []


def test_list_runs_unknown_task(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    assert client.get("/api/scheduled-tasks/nope/runs").status_code == 404


def test_list_runs_rejects_bad_limit(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    task = _make_task(db, tmp_path)
    assert client.get(f"/api/scheduled-tasks/{task['id']}/runs?limit=0").status_code == 422
    assert client.get(f"/api/scheduled-tasks/{task['id']}/runs?limit=999").status_code == 422


def test_list_runs_respects_limit(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    task = _make_task(db, tmp_path)
    for _ in range(5):
        db.create_run(task["id"])
    runs = client.get(
        f"/api/scheduled-tasks/{task['id']}/runs?limit=2"
    ).json()["runs"]
    assert len(runs) == 2
