"""HTTP 层回归：REST 端点（sessions / projects / settings / files / health）
与 stream_chat SSE 主链路（fake 模型全链路）。此前这些端点零覆盖，
协议改动只能靠手测回归。"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import SimpleChatModel


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "http.db"))
    from app import db

    db.init_db()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_reports_provider_and_tools(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["tools"], int)


# ---------------------------------------------------------------------------
# sessions CRUD
# ---------------------------------------------------------------------------


def test_session_crud_roundtrip(client):
    created = client.post(
        "/api/sessions", json={"title": "HTTP 测试", "locale": "zh-CN"}
    )
    assert created.status_code == 201
    session = created.json()
    session_id = session["id"]
    assert session["title"] == "HTTP 测试"

    listing = client.get("/api/sessions")
    assert listing.status_code == 200
    sessions = listing.json()
    if isinstance(sessions, dict):
        sessions = sessions.get("sessions") or []
    assert any(s["id"] == session_id for s in sessions)

    detail = client.get(f"/api/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["session"]["title"] == "HTTP 测试"

    patched = client.patch(
        f"/api/sessions/{session_id}", json={"title": "改名了"}
    )
    assert patched.status_code == 200
    renamed = client.get(f"/api/sessions/{session_id}")
    assert renamed.json()["session"]["title"] == "改名了"

    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


def test_session_rejects_bad_approval_mode(client):
    resp = client.post(
        "/api/sessions", json={"approval_mode": "yolo"}
    )
    assert resp.status_code == 400


def test_session_404_on_missing_project(client):
    resp = client.post("/api/sessions", json={"project_id": "no-such"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# projects + settings + files
# ---------------------------------------------------------------------------


def test_project_create_and_list(client):
    created = client.post(
        "/api/projects", json={"name": "项目A", "path": "/tmp/proj-a"}
    )
    assert created.status_code == 201
    listing = client.get("/api/projects")
    assert listing.status_code == 200
    projects = listing.json()
    if isinstance(projects, dict):
        projects = projects.get("projects") or list(projects.values())
    assert any(p["name"] == "项目A" for p in projects)


def test_settings_get_and_put_username(client):
    got = client.get("/api/settings")
    assert got.status_code == 200
    assert "provider" in got.json()

    put = client.put("/api/settings", json={"username": "测试用户"})
    assert put.status_code == 200
    assert client.get("/api/settings").json()["username"] == "测试用户"


def test_files_list_shape(client):
    resp = client.get("/api/files")
    assert resp.status_code == 200
    body = resp.json()
    assert "categories" in body
    assert isinstance(body["categories"], list)


# ---------------------------------------------------------------------------
# stream_chat SSE 主链路（fake 模型走生产同一条 agent 链路）
# ---------------------------------------------------------------------------


class _PlainFakeModel(SimpleChatModel):
    """普通文本模型：无工具调用，直接产出一段中文回答。"""

    @property
    def _llm_type(self) -> str:
        return "plain-fake"

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        return "你好，我是 Divine。"


def test_stream_chat_full_chain(client, monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(
        orchestrator, "_build_llm", lambda **kw: _PlainFakeModel()
    )
    session_id = client.post(
        "/api/sessions", json={"title": "流式", "locale": "zh-CN"}
    ).json()["id"]

    with client.stream(
        "POST",
        "/api/stream_chat",
        json={
            "question": "打个招呼",
            "session_id": session_id,
            "approval_mode": "full",
            "locale": "zh-CN",
            "tool_mode": "react",
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(chunk for chunk in resp.iter_text())

    assert "event: message" in body
    assert "你好，我是 Divine。" in body
    assert "event: done" in body

    # 回答必须落库：刷新（重新拉会话）后可见
    from app import db

    rows = db.list_messages(session_id)
    roles = [m["role"] for m in rows]
    assert roles[:2] == ["user", "assistant"]
    assert "你好，我是 Divine。" in rows[1]["content"]


def test_stream_chat_persists_user_message_before_stream(client):
    """流式开始前用户消息已落库（断连也不丢问句）。"""
    session_id = client.post("/api/sessions", json={"locale": "zh-CN"}).json()[
        "id"
    ]
    with client.stream(
        "POST",
        "/api/stream_chat",
        json={
            "question": "这个问题会被取消",
            "session_id": session_id,
            "approval_mode": "full",
            "locale": "zh-CN",
        },
    ) as resp:
        assert resp.status_code == 200
        # 不消费完整流：读到第一个事件即断开，模拟客户端中断
        for _ in resp.iter_lines():
            break

    from app import db

    rows = db.list_messages(session_id)
    assert any(
        m["role"] == "user" and "这个问题会被取消" in m["content"]
        for m in rows
    )


def test_stream_chat_rejects_empty_question(client):
    resp = client.post(
        "/api/stream_chat", json={"question": "", "locale": "zh-CN"}
    )
    assert resp.status_code == 200  # SSE 错误也走 200 + error 事件
    assert "event: error" in resp.text
    assert "invalid_request" in resp.text
