"""history_for_model 尾窗化：行集与旧全量扫描实现等价 + 端到端不变量。

组装逻辑（附件重组/空回复跳过/摘要前置）在两种取数方式下共享，
因此 _fetch_window 行集等价 ⇒ 最终输出等价。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))
    from app import db

    db.init_db()
    return db


def _legacy_window_ids(db, session_id: str, limit: int, until_id: str | None):
    """旧实现：升序全量加载 → 截断 → 尾切片，返回选中的消息 id 序列。"""
    from app.db.connection import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
        messages = [dict(row) for row in rows]
    if until_id:
        for index, message in enumerate(messages):
            if message["id"] == until_id:
                messages = messages[: index + 1]
                break
    return [m["id"] for m in messages[-limit:]]


def _build_session(db, rounds: int = 15):
    """构造含工具轮次/空回复/附件的会话（同一秒内批量插入，覆盖并列排序）。"""
    session = db.create_session("窗口测试")
    user_ids: list[str] = []
    for i in range(rounds):
        user = db.add_message(session["id"], "user", f"问题 {i}")
        user_ids.append(user["id"])
        if i % 3 == 0:
            assistant = db.add_message(session["id"], "assistant", "")
            calls = [{"id": f"call-{i}", "name": "read_file", "args": {}}]
            db.add_message_part(
                assistant["id"], "tool_calls", json.dumps(calls), order=0
            )
            db.add_message(
                session["id"],
                "tool",
                json.dumps({"tool_call_id": f"call-{i}", "output": "ok"}),
            )
            db.add_message(session["id"], "assistant", f"回答 {i}")
        elif i % 3 == 1:
            # 附件用户消息：file part 应被 history 重组进 user turn
            db.add_message_part(
                user["id"], "file", json.dumps({"name": f"f{i}.txt"}), order=0
            )
            db.add_message(session["id"], "assistant", f"附件回答 {i}")
        else:
            # 空回复应被跳过
            db.add_message(session["id"], "assistant", "")
    return session, user_ids


def test_window_rows_match_legacy_slice(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session, _ = _build_session(db)

    from app.db.connection import get_conn
    from app.db.history import _fetch_window

    for limit in (2, 5, 20, 100):
        with get_conn() as conn:
            windowed = _fetch_window(conn, session["id"], limit, None)
        expected = _legacy_window_ids(db, session["id"], limit, None)
        assert [m["id"] for m in windowed] == expected, (
            f"limit={limit} 尾窗行集与旧实现不一致"
        )


def test_until_message_id_truncates(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session, user_ids = _build_session(db, rounds=10)

    from app.db.connection import get_conn
    from app.db.history import _fetch_window

    cut = user_ids[6]
    with get_conn() as conn:
        windowed = _fetch_window(conn, session["id"], 50, cut)
    expected = _legacy_window_ids(db, session["id"], 50, cut)
    assert [m["id"] for m in windowed] == expected


def test_until_missing_id_returns_full_window(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session, _ = _build_session(db, rounds=6)

    from app.db.connection import get_conn
    from app.db.history import _fetch_window

    with get_conn() as conn:
        windowed = _fetch_window(conn, session["id"], 50, "nonexistent-id")
    expected = _legacy_window_ids(db, session["id"], 50, None)
    assert [m["id"] for m in windowed] == expected


def test_window_does_not_split_tool_call_group(monkeypatch, tmp_path):
    """窗口起点落在 tool 结果上时应整组丢弃，不产生无主的 tool 消息。"""
    db = _setup_db(monkeypatch, tmp_path)
    session, _ = _build_session(db, rounds=20)

    from app.db.history import history_for_model

    for limit in range(2, 40):
        result = history_for_model(session["id"], limit=limit)
        for index, item in enumerate(result):
            if item["role"] == "tool":
                # tool 消息前必须存在声明了该 call 的 assistant
                assert index > 0 and result[index - 1]["role"] == "assistant"
                assert result[index - 1].get("tool_calls"), (
                    f"limit={limit} 出现悬空 tool 消息"
                )


def test_summary_prepended_outside_window(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session, _ = _build_session(db, rounds=5)

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO session_summaries (session_id, summary, created_at, "
            "updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            (session["id"], "早期对话摘要内容"),
        )
        conn.commit()

    from app.db.history import history_for_model

    result = history_for_model(session["id"], limit=3)
    assert result[0]["role"] == "system"
    assert "早期对话摘要" in result[0]["content"]
    assert len(result) == 4  # 摘要 + 窗口 3 条


def test_attachment_rehydrated_in_window(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session, _ = _build_session(db, rounds=6)

    from app.db.history import history_for_model

    result = history_for_model(session["id"], limit=50)
    user_texts = [
        str(m.get("content"))
        for m in result
        if m["role"] == "user"
    ]
    assert any("[附件：" in text for text in user_texts)


def test_empty_session(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("空会话")

    from app.db.history import history_for_model

    assert history_for_model(session["id"], limit=10) == []

def _add_tool_result(db, session_id, call_id, output="ok"):
    """真实写入路径：tool 消息 + tool_result part（history 从 part 解析 call_id）。"""
    tool_msg = db.add_message(
        session_id, "tool", json.dumps({"tool_call_id": call_id, "output": output})
    )
    db.add_message_part(
        tool_msg["id"], "tool_result", json.dumps({"tool_call_id": call_id}), order=0
    )
    return tool_msg


# ---- 残缺 tool_calls 组兜底（会话中断/工具失败残留） ----

def _orphan_session(db, partial: bool):
    """构造含中断 tool_calls 的会话。

    partial=False：assistant(tool_calls) 后完全无 tool 响应（中断）。
    partial=True：assistant(tool_calls A+B) 只有 tool(A) 入库（部分执行）。
    """
    session = db.create_session("残缺组测试")
    db.add_message(session["id"], "user", "帮我做两件事")
    if partial:
        assistant = db.add_message(session["id"], "assistant", "")
        calls = [
            {"id": "call-a", "name": "read_file", "args": {}},
            {"id": "call-b", "name": "grep_files", "args": {}},
        ]
        db.add_message_part(
            assistant["id"], "tool_calls", json.dumps(calls), order=0
        )
        # 只有 call-a 有响应，call-b 缺失（模拟中断/执行失败）
        _add_tool_result(db, session["id"], "call-a")
    else:
        assistant = db.add_message(session["id"], "assistant", "")
        calls = [{"id": "call-x", "name": "read_file", "args": {}}]
        db.add_message_part(
            assistant["id"], "tool_calls", json.dumps(calls), order=0
        )
        # 无 tool 响应直接结束
    return session


def test_interrupted_tool_calls_dropped(monkeypatch, tmp_path):
    """完全中断：尾部 assistant tool_calls 无响应 → 从发给模型的历史中剔除。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = _orphan_session(db, partial=False)

    from app.db.history import history_for_model

    result = history_for_model(session["id"], limit=50)
    assert result, "历史不应为空"
    assert result[-1]["role"] == "user", (
        "末尾不应残留未配对的 assistant tool_calls，实际末尾: "
        f"{result[-1].get('role')}"
    )
    assert not any(msg.get("tool_calls") for msg in result), (
        "残缺的 assistant tool_calls 不应出现在模型历史中"
    )


def test_partial_tool_calls_group_dropped(monkeypatch, tmp_path):
    """部分执行：并行 tool_calls 只回了 A → 残缺组（assistant + tool A）整体剔除。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = _orphan_session(db, partial=True)

    from app.db.history import history_for_model

    result = history_for_model(session["id"], limit=50)
    assert result[-1]["role"] == "user", (
        "残缺组应被整体剔除（assistant tool_calls + 已回的单条 tool），"
        f"实际末尾: {result[-1].get('role')}"
    )
    assert not any(msg.get("role") == "tool" for msg in result), (
        "残缺组的 tool 结果不应孤立存在（其 assistant 已被剔除）"
    )


def test_complete_tool_group_kept(monkeypatch, tmp_path):
    """对照组：完整配对的 tool_calls 组不受影响（防误删回归）。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = _orphan_session(db, partial=True)
    # 补齐 call-b 的响应 → 组变完整
    _add_tool_result(db, session["id"], "call-b")
    db.add_message(session["id"], "assistant", "都完成了")

    from app.db.history import history_for_model

    result = history_for_model(session["id"], limit=50)
    assert any(msg.get("tool_calls") for msg in result), "完整组应保留"
    assert sum(1 for msg in result if msg.get("role") == "tool") == 2, (
        "两个 tool 响应都应保留"
    )
    assert result[-1]["role"] == "assistant"
