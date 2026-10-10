"""A2UI 的持久化（S3）与交互回流（S4）回归。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §5.3 / §5.5 / §8。

覆盖三块：

* **S3 面板最终态落库** —— 回合收尾时从 ``tool_calls`` 的 arguments 重建
  面板并挂成 ``ui_surface`` part（无状态、可重启、天然幂等）；
* **S3 编辑态表** —— ``ui_surface_states`` 的覆盖写 / 按会话取 / 清理，
  以及两个 HTTP 端点；
* **S4 动作回流** —— ``_surface_action_question`` 必须把求值结果写进**可见
  正文**（``message_parts`` 不进模型上下文），幂等键窗口，以及开关关闭 /
  会话不存在 / 会话流式中三条边界。

刻意不在这里跑完整 agent 回合（那会拖进模型依赖）：动作端点只测
**不进入流式生成器**的那几条分支，流式分支由 ``test_http_api.py`` 的
fake 模型链路覆盖。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.state.persistence import _collect_ui_surfaces, _persist_new_messages
from app.tools.ui.catalog import CATALOG_ID


def _sample_args() -> dict:
    """一块最小合法面板（root + Text）。"""
    return {
        "surfaceId": "cost-panel",
        "title": "成本",
        "components": [
            {"id": "root", "component": "Column", "children": ["t"]},
            {"id": "t", "component": "Text", "text": "去重后的结论"},
        ],
        "data": {},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a2ui.db"))
    from app import db

    db.init_db()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """只初始化 DB，不起 FastAPI（给纯 db / 纯函数测试用）。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a2ui-unit.db"))
    from app import db

    db.init_db()
    return db


# ---------------------------------------------------------------------------
# S3 · 面板最终态：从 tool_calls arguments 重建
# ---------------------------------------------------------------------------


def test_collect_ui_surfaces_rebuilds_from_arguments() -> None:
    surfaces = _collect_ui_surfaces([{"name": "render_ui", "args": _sample_args()}])
    assert len(surfaces) == 1
    surface = surfaces[0]
    assert surface["surfaceId"] == "cost-panel"
    assert [c["id"] for c in surface["components"]] == ["root", "t"]


def test_collect_ui_surfaces_ignores_other_tools_and_bad_args() -> None:
    calls = [
        {"name": "generate_chart", "args": {"type": "bar"}},
        {"name": "render_ui", "args": {"surfaceId": "broken"}},  # 无 root → 不合法
        {"name": "render_ui", "args": "not-a-dict"},
        {"name": "render_ui", "args": {}},  # 空 IR → 不合法
    ]
    # 全部跳过，且**不抛**（落库不能因为一块面板出问题而整轮失败）
    assert _collect_ui_surfaces(calls) == []


def test_collect_ui_surfaces_swallows_exceptions(monkeypatch) -> None:
    import app.agent.state.persistence as persistence
    import app.tools.ui.ir as ir_mod

    monkeypatch.setattr(
        ir_mod, "extract_surface", lambda args: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert _collect_ui_surfaces([{"name": "render_ui", "args": _sample_args()}]) == []
    assert persistence is not None


def test_persist_new_messages_attaches_ui_surface_part(db_env) -> None:
    db = db_env
    session = db.create_session("落库测试", locale="zh-CN")
    session_id = session["id"]

    # 与生产同形：messages 里含本轮 input 的 user 消息，落库只处理它之后的部分。
    messages = [
        HumanMessage(content="给我看本月成本结构"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "render_ui", "args": _sample_args(), "id": "call_1"},
            ],
        ),
        ToolMessage(content="✓ 已渲染交互面板", tool_call_id="call_1"),
        AIMessage(content="结论如下。"),
    ]
    last_id = _persist_new_messages(session_id, [messages[0]], messages, {})
    assert last_id

    parts = db.list_message_parts(last_id)
    ui_parts = [part for part in parts if part["type"] == "ui_surface"]
    assert len(ui_parts) == 1
    payload = json.loads(ui_parts[0]["content"])
    assert payload["surfaceId"] == "cost-panel"
    # 面板挂**正文消息**，不是承载 tool_calls 的那条空消息（前端会跳过后者）
    assert payload["components"][1]["text"] == "去重后的结论"
    assert db.get_message(last_id)["content"] == "结论如下。"


def test_persist_new_messages_parks_surface_on_tool_turn(db_env) -> None:
    """只调工具没输出正文时，面板退到工具轮次那条消息上（design 028 §8.5）。

    以前是"没有正文消息宁可不落"。但静默回合（面板动作）要按消息把面板搬回
    原面板所在的那条消息 —— 没有承载者就等于"只更新面板、不说话"的一轮把
    面板整块丢掉。正常回合不受影响：前端会跳过这条空 assistant 消息，
    读不到它的 parts。
    """
    db = db_env
    session_id = db.create_session("无正文", locale="zh-CN")["id"]
    messages = [
        HumanMessage(content="给我看成本结构"),
        AIMessage(
            content="",
            tool_calls=[{"name": "render_ui", "args": _sample_args(), "id": "call_1"}],
        ),
        ToolMessage(content="✓", tool_call_id="call_1"),
    ]
    last_id = _persist_new_messages(session_id, [messages[0]], messages, {})
    # 返回值语义不变：仍然只表示"最后一条 assistant 正文消息"，这里是 None
    assert last_id is None

    parked = [
        (message, part)
        for message in db.list_messages(session_id)
        for part in db.list_message_parts(message["id"])
        if part["type"] == "ui_surface"
    ]
    assert len(parked) == 1
    holder, part = parked[0]
    assert holder["role"] == "assistant"
    assert holder["content"] == ""
    assert json.loads(part["content"])["surfaceId"] == "cost-panel"


# ---------------------------------------------------------------------------
# S3 · 编辑态表（ui_surface_states）
# ---------------------------------------------------------------------------


def test_ui_surface_state_upsert_overwrites_by_surface_id(db_env) -> None:
    db = db_env
    db.save_ui_surface_state("s1", {"target": {"labor": 30}}, session_id="sess")
    db.save_ui_surface_state("s1", {"target": {"labor": 55}}, session_id="sess")
    rows = db.list_session_ui_surface_states("sess")
    # 按 surface_id 覆盖写，不堆行
    assert len(rows) == 1
    assert rows[0]["data"] == {"target": {"labor": 55}}


def test_ui_surface_state_listed_per_session_and_cleared(db_env) -> None:
    db = db_env
    db.save_ui_surface_state("s1", {"a": 1}, session_id="sess-a")
    db.save_ui_surface_state("s2", {"b": 2}, session_id="sess-b")
    assert [row["surface_id"] for row in db.list_session_ui_surface_states("sess-a")] == ["s1"]

    db.clear_ui_surface_state("s1")
    assert db.list_session_ui_surface_states("sess-a") == []

    db.clear_session_ui_surface_states("sess-b")
    assert db.list_session_ui_surface_states("sess-b") == []


def test_ui_surface_state_http_endpoints(client) -> None:
    session_id = client.post(
        "/api/sessions", json={"title": "编辑态", "locale": "zh-CN"}
    ).json()["id"]

    unknown = client.post(
        "/api/sessions/does-not-exist/ui-surface-state",
        json={"surface_id": "s1", "data": {"a": 1}},
    )
    assert unknown.status_code == 404

    saved = client.post(
        f"/api/sessions/{session_id}/ui-surface-state",
        json={"surface_id": "s1", "message_id": "m1", "data": {"target": {"labor": 25}}},
    )
    assert saved.status_code == 200 and saved.json()["ok"] is True

    listed = client.get(f"/api/sessions/{session_id}/ui-surface-states")
    assert listed.status_code == 200
    states = listed.json()["states"]
    assert len(states) == 1
    assert states[0]["surface_id"] == "s1"
    assert states[0]["message_id"] == "m1"
    assert states[0]["data"] == {"target": {"labor": 25}}

    # 覆盖写：同一 surface_id 再写一次不堆行
    client.post(
        f"/api/sessions/{session_id}/ui-surface-state",
        json={"surface_id": "s1", "data": {"target": {"labor": 60}}},
    )
    assert len(client.get(f"/api/sessions/{session_id}/ui-surface-states").json()["states"]) == 1

    # 删除会话必须显式清表：ui_surface_states 没有外键，不指望 CASCADE
    assert client.delete(f"/api/sessions/{session_id}").status_code == 204
    from app import db

    assert db.list_session_ui_surface_states(session_id) == []


def test_clear_session_wipes_ui_surface_states(client) -> None:
    session_id = client.post(
        "/api/sessions", json={"title": "清空", "locale": "zh-CN"}
    ).json()["id"]
    client.post(
        f"/api/sessions/{session_id}/ui-surface-state",
        json={"surface_id": "s9", "data": {"a": 1}},
    )
    assert client.post(f"/api/sessions/{session_id}/clear").status_code == 200
    assert client.get(f"/api/sessions/{session_id}/ui-surface-states").json()["states"] == []


# ---------------------------------------------------------------------------
# S4 · 动作 → 可见正文
# ---------------------------------------------------------------------------


def test_surface_action_question_inlines_context_values() -> None:
    from app.api.chat import _surface_action_question
    from app.schemas import SurfaceActionRequest

    request = SurfaceActionRequest(
        session_id="s1",
        action_id="a1",
        name="recalc",
        label="重新测算",
        context={"labor": 25, "scope": "全量"},
    )
    text = _surface_action_question(request)
    # 结构化参数必须落进正文：message_parts 不进模型上下文
    assert text == "重新测算（labor=25，scope=全量）"


def test_surface_action_question_without_context_and_with_long_value() -> None:
    from app.api.chat import _MAX_CONTEXT_VALUE_CHARS, _surface_action_question
    from app.schemas import SurfaceActionRequest

    plain = SurfaceActionRequest(session_id="s1", action_id="a1", name="refresh")
    assert _surface_action_question(plain) == "refresh"

    long_value = "x" * (_MAX_CONTEXT_VALUE_CHARS * 3)
    noisy = SurfaceActionRequest(
        session_id="s1", action_id="a2", name="recalc", context={"blob": long_value}
    )
    text = _surface_action_question(noisy)
    assert text.endswith("…）")
    assert len(text) < _MAX_CONTEXT_VALUE_CHARS * 2


def test_remember_surface_action_is_idempotent_in_window() -> None:
    from app.api.chat import _SURFACE_ACTION_SEEN, _remember_surface_action

    _SURFACE_ACTION_SEEN.clear()
    assert _remember_surface_action("dup") is True
    assert _remember_surface_action("dup") is False  # 60s 内重复 → 不起新回合
    assert _remember_surface_action("other") is True
    _SURFACE_ACTION_SEEN.clear()


def test_remember_surface_action_expires_and_prunes() -> None:
    import time

    from app.api.chat import _SURFACE_ACTION_SEEN, _remember_surface_action

    _SURFACE_ACTION_SEEN.clear()
    _SURFACE_ACTION_SEEN["stale"] = time.monotonic() - 3600
    assert _remember_surface_action("fresh") is True
    # 过期项在登记时顺手淘汰，不在窗口内的 id 可以复用
    assert "stale" not in _SURFACE_ACTION_SEEN
    assert _remember_surface_action("stale") is True
    _SURFACE_ACTION_SEEN.clear()


# ---------------------------------------------------------------------------
# S4 · 动作端点边界
# ---------------------------------------------------------------------------


def test_surface_action_404_when_flag_off(client, monkeypatch) -> None:
    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "a2ui_enabled", lambda: False)
    resp = client.post(
        "/api/chat/surface-action",
        json={"session_id": "any", "action_id": "a1", "name": "submit"},
    )
    assert resp.status_code == 404


def test_surface_action_404_for_unknown_session(client, monkeypatch) -> None:
    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "a2ui_enabled", lambda: True)
    resp = client.post(
        "/api/chat/surface-action",
        json={"session_id": "nope", "action_id": "a1", "name": "submit"},
    )
    assert resp.status_code == 404


def test_surface_action_409_while_session_streaming(client, monkeypatch) -> None:
    import asyncio

    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "a2ui_enabled", lambda: True)
    session_id = client.post(
        "/api/sessions", json={"title": "流式中", "locale": "zh-CN"}
    ).json()["id"]
    chat_api._CANCEL_EVENTS[session_id] = asyncio.Event()
    try:
        resp = client.post(
            "/api/chat/surface-action",
            json={"session_id": session_id, "action_id": "a1", "name": "submit"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "session_busy"
    finally:
        chat_api._CANCEL_EVENTS.pop(session_id, None)


def test_surface_action_dedupes_without_starting_a_turn(client, monkeypatch) -> None:
    """幂等命中：回一个立即结束的 done 流（前端不会重复追加回合）。"""
    import time

    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "a2ui_enabled", lambda: True)
    session_id = client.post(
        "/api/sessions", json={"title": "幂等", "locale": "zh-CN"}
    ).json()["id"]
    chat_api._SURFACE_ACTION_SEEN.clear()
    chat_api._SURFACE_ACTION_SEEN["same-action"] = time.monotonic()
    try:
        with client.stream(
            "POST",
            "/api/chat/surface-action",
            json={"session_id": session_id, "action_id": "same-action", "name": "submit"},
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        assert "event: done" in body
        assert '"deduped": true' in body
        # 没有起新回合 → 会话里不留 user 消息
        from app import db

        assert db.list_messages(session_id) == []
    finally:
        chat_api._SURFACE_ACTION_SEEN.clear()


def test_surface_action_schema_requires_action_id_and_name(client) -> None:
    resp = client.post("/api/chat/surface-action", json={"session_id": "s1", "name": "submit"})
    assert resp.status_code == 422


def test_catalog_id_is_used_by_messages() -> None:
    """面板消息里的 catalogId 必须与目录真源一致（前端会据此校验）。"""
    from app.tools.ui.versions.v0_9_1 import to_messages

    normalized = _collect_ui_surfaces([{"name": "render_ui", "args": _sample_args()}])[0]
    messages = to_messages(normalized)
    assert messages[0]["createSurface"]["catalogId"] == CATALOG_ID


# ---------------------------------------------------------------------------
# S5 · 静默回合：打标 + 面板搬回原消息（design 028 §8.5）
# ---------------------------------------------------------------------------


def _panel_ir(surface_id: str, component_id: str) -> str:
    return json.dumps(
        {
            "surfaceId": surface_id,
            "components": [{"id": component_id, "component": "Text", "text": "x"}],
            "data": {},
        },
        ensure_ascii=False,
    )


def _seed_action_turn(db, session_id: str, *, with_surface: bool = True) -> list[str]:
    """造"本轮"三条消息：user 动作 / assistant 正文（可含面板）/ tool 结果。"""
    ids = [db.add_message(session_id, "user", "提交参数（labor_input=20）")["id"]]
    assistant = db.add_message(session_id, "assistant", "已按新参数重算。")
    ids.append(assistant["id"])
    if with_surface:
        db.add_message_part(
            assistant["id"], "ui_surface", _panel_ir("cost-panel", "new"), order=100
        )
    ids.append(db.add_message(session_id, "tool", "✓ 已更新面板")["id"])
    return ids


def _parts_of_type(db, message_id: str, part_type: str) -> list[dict]:
    return [
        json.loads(part["content"])
        for part in db.list_message_parts(message_id)
        if part["type"] == part_type
    ]


def test_finalize_surface_turn_moves_panel_back_to_owner(db_env) -> None:
    from app.api.chat import _finalize_surface_turn

    db = db_env
    session_id = db.create_session("静默回合", locale="zh-CN")["id"]
    # 面板挂在更早的一条消息上，随后才是"动作前的最后一条消息"（边界）。
    # 真实场景里用户就是往上滚到旧面板上去操作的。
    owner = db.add_message(session_id, "assistant", "结论如下。")
    db.add_message_part(
        owner["id"], "ui_surface", _panel_ir("cost-panel", "old"), order=100
    )
    boundary = db.add_message(session_id, "user", "给我看成本结构")

    fresh_ids = _seed_action_turn(db, session_id)
    _finalize_surface_turn(session_id, boundary["id"], owner["id"])

    rows = {row["id"]: row for row in db.list_messages(session_id)}
    # 本轮消息全部打标（前端据此把这一轮滤成不成气泡）
    assert all(rows[mid]["source"] == "surface_action" for mid in fresh_ids)
    # 边界之前与面板所属的消息不受影响
    assert rows[boundary["id"]]["source"] == "normal"
    assert rows[owner["id"]]["source"] == "normal"

    # 面板原地更新：同 surfaceId 是覆盖而非叠加，且部件已从本轮消息搬走
    assert [
        s["components"][0]["id"]
        for s in _parts_of_type(db, owner["id"], "ui_surface")
    ] == ["new"]
    assert all(
        _parts_of_type(db, mid, "ui_surface") == [] for mid in fresh_ids
    )
    # 本轮正文降级成面板底部一行说明
    assert _parts_of_type(db, owner["id"], "surface_note") == [
        {"text": "已按新参数重算。", "updated": True}
    ]


def test_finalize_surface_turn_keeps_panel_when_turn_has_none(db_env) -> None:
    from app.api.chat import _finalize_surface_turn

    db = db_env
    session_id = db.create_session("无面板", locale="zh-CN")["id"]
    # 面板挂在更早的一条消息上，随后才是"动作前的最后一条消息"（边界）。
    # 真实场景里用户就是往上滚到旧面板上去操作的。
    owner = db.add_message(session_id, "assistant", "结论如下。")
    db.add_message_part(
        owner["id"], "ui_surface", _panel_ir("cost-panel", "old"), order=100
    )
    boundary = db.add_message(session_id, "user", "给我看成本结构")

    _seed_action_turn(db, session_id, with_surface=False)
    _finalize_surface_turn(session_id, boundary["id"], owner["id"])

    # 本轮没有面板产出 → 旧面板必须留着，只追加"未返回更新"的说明
    assert [
        s["components"][0]["id"]
        for s in _parts_of_type(db, owner["id"], "ui_surface")
    ] == ["old"]
    assert _parts_of_type(db, owner["id"], "surface_note") == [
        {"text": "已按新参数重算。", "updated": False}
    ]


def test_finalize_surface_turn_marks_only_when_owner_missing(db_env) -> None:
    from app.api.chat import _finalize_surface_turn

    db = db_env
    session_id = db.create_session("目标缺失", locale="zh-CN")["id"]
    boundary = db.add_message(session_id, "user", "给我看成本结构")
    fresh_ids = _seed_action_turn(db, session_id)

    _finalize_surface_turn(session_id, boundary["id"], "no-such-message")

    rows = {row["id"]: row for row in db.list_messages(session_id)}
    assert all(rows[mid]["source"] == "surface_action" for mid in fresh_ids)
    # 没有承载者 → 不搬迁，本轮面板留在原消息里（前端照常渲染那条消息，
    # 比丢面板好）
    assert [
        s["components"][0]["id"]
        for s in _parts_of_type(db, fresh_ids[1], "ui_surface")
    ] == ["new"]


def test_surface_action_question_asks_to_refresh_same_panel() -> None:
    from app.api.chat import _surface_action_question
    from app.schemas import SurfaceActionRequest

    request = SurfaceActionRequest(
        session_id="s1",
        action_id="a1",
        name="submit",
        label="提交参数",
        context={"labor_input": 20},
        surface_id="cost_dashboard_v2",
    )
    text = _surface_action_question(request)
    # 求值结果照旧落进正文（message_parts 不进模型上下文）
    assert "提交参数（labor_input=20）" in text
    # 面板归属与"原地更新"指示必须进正文：结构化字段模型看不到，
    # 不写的话模型会另起一块面板 → 用户又得滚下去找结果
    assert "surface_id=cost_dashboard_v2" in text
    assert "不要新建面板" in text


def test_session_preview_skips_surface_action_messages(db_env) -> None:
    db = db_env
    session_id = db.create_session("预览", locale="zh-CN")["id"]
    db.add_message(session_id, "user", "真实的用户提问")
    silent = db.add_message(session_id, "user", "提交参数（labor_input=20）")
    db.mark_messages_source([silent["id"]], "surface_action")

    session = next(item for item in db.list_sessions() if item["id"] == session_id)
    # 会话列表不该显示面板回执当预览
    assert session["last_message"] == "真实的用户提问"
