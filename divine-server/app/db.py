from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import db_path
from .file_types import is_image_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新对话',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_parts (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tool_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    input TEXT NOT NULL DEFAULT '{}',
    output TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_parts_message ON message_parts(message_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_session ON tool_runs(session_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _new_id() -> str:
    return uuid.uuid4().hex


def create_session(title: str | None = None) -> dict[str, Any]:
    session_id = _new_id()
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title or "新对话", now, now),
        )
        conn.commit()
    return get_session(session_id)


def get_session(session_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_sessions() -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def update_session(session_id: str, title: str | None = None) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title if title is not None else session["title"], _now(), session_id),
        )
        conn.commit()
    return get_session(session_id)


def touch_session(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        conn.commit()


def delete_session(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def clear_messages(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM tool_runs WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE sessions SET title = '新对话', updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        conn.commit()


def add_message(
    session_id: str, role: str, content: str, created_at: str | None = None
) -> dict[str, Any]:
    message_id = _new_id()
    now = created_at or _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()
    return get_message(message_id)


def get_message(message_id: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return dict(row)


def list_messages(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_message_part(
    message_id: str, part_type: str, content: str, order: int = 0
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO message_parts (id, message_id, type, content, \"order\") VALUES (?, ?, ?, ?, ?)",
            (_new_id(), message_id, part_type, content, order),
        )
        conn.commit()


def list_message_parts(message_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM message_parts WHERE message_id = ? ORDER BY \"order\" ASC, rowid ASC",
            (message_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_tool_run(
    session_id: str,
    tool_name: str,
    status: str,
    input_data: dict[str, Any],
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _new_id()
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO tool_runs (id, session_id, tool_name, status, input, output, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                tool_name,
                status,
                _json(input_data),
                _json(output) if output else None,
                now,
                now if status in ("done", "error") else None,
            ),
        )
        conn.commit()
    return get_tool_run(run_id)


def update_tool_run(
    run_id: str, status: str, output: dict[str, Any] | None = None
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE tool_runs SET status = ?, output = ?, finished_at = ? WHERE id = ?",
            (status, _json(output) if output else None, _now(), run_id),
        )
        conn.commit()


def list_tool_runs(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM tool_runs WHERE session_id = ? ORDER BY started_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_tool_run(run_id: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM tool_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return dict(row)


def history_for_model(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Model-facing history; file attachments are rehydrated into user turns."""
    messages = list_messages(session_id)[-limit:]
    result: list[dict[str, Any]] = []
    for message in messages:
        content = message["content"]
        if message["role"] == "user":
            blocks: list[str] = []
            for part in list_message_parts(message["id"]):
                if part["type"] != "file":
                    continue
                try:
                    meta = json.loads(part["content"])
                except json.JSONDecodeError:
                    meta = {"name": part["content"]}
                name = meta.get("name") or "附件"
                path = meta.get("path") or ""
                body = meta.get("content") or ""
                error = meta.get("error") or ""
                path_line = f"文件本地路径：{path}\n" if path else ""
                if path and is_image_path(path):
                    blocks.append(
                        f"[附件图片：{name}]\n图片本地路径：{path}\n"
                        "请调用 read_image 工具读取这张图片并分析内容，再结合分析结果回答用户的问题。"
                    )
                elif error:
                    if body:
                        blocks.append(
                            f"[附件：{name}]\n{path_line}读取失败: {error}\n"
                            "这不是图片文件，请直接分析以下内容，不要调用 read_image。\n"
                            f"```\n{body}\n```"
                        )
                    else:
                        blocks.append(
                            f"[附件：{name}]\n{path_line}读取失败: {error}"
                        )
                elif body:
                    blocks.append(
                        f"[附件：{name}]\n{path_line}"
                        "这不是图片文件，请直接分析以下内容，不要调用 read_image。\n"
                        f"```\n{body}\n```"
                    )
                else:
                    blocks.append(f"[附件：{name}]\n{path_line}".rstrip())
            if blocks:
                suffix = "\n\n".join(blocks)
                content = f"{content}\n\n{suffix}" if content else suffix
        if message["role"] == "assistant":
            think_parts = [
                part["content"]
                for part in list_message_parts(message["id"])
                if part["type"] == "think"
            ]
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": content,
            }
            if think_parts:
                entry["reasoning_content"] = "\n".join(think_parts)
            result.append(entry)
            continue
        if content:
            result.append({"role": message["role"], "content": content})
    return result


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


def load_session(session_id: str) -> dict[str, Any]:
    """Full message view used by the frontend when restoring history."""
    messages = []
    for message in list_messages(session_id):
        messages.append(
            {
                **message,
                "parts": list_message_parts(message["id"]),
            }
        )
    return {
        "session": get_session(session_id),
        "messages": messages,
        "tool_runs": list_tool_runs(session_id),
    }
