from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import db_path, workspace_dir
from .file_types import is_image_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT 'folder',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新对话',
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    approval_mode TEXT NOT NULL DEFAULT 'ask',
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

CREATE TABLE IF NOT EXISTS agent_todos (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    "index" INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_parts_message ON message_parts(message_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_session ON tool_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_todos_session ON agent_todos(session_id);
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
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sessions)")
        }
        if "project_id" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT")
        if "approval_mode" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN approval_mode TEXT "
                "NOT NULL DEFAULT 'ask'"
            )
        project_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(projects)")
        }
        if "icon" not in project_columns:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN icon TEXT NOT NULL DEFAULT 'folder'"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_project "
            "ON sessions(project_id)"
        )
        conn.commit()
    default = default_project()
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE sessions SET project_id = ? WHERE project_id IS NULL",
            (default["id"],),
        )
        conn.commit()


def _new_id() -> str:
    return uuid.uuid4().hex


def create_project(
    name: str, path: str, icon: str | None = None
) -> dict[str, Any]:
    project_id = _new_id()
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO projects "
            "(id, name, path, icon, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name, path, icon or "folder", now, now),
        )
        conn.commit()
    return get_project(project_id)


def default_project() -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM projects ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
    if row:
        return dict(row)
    workspace = workspace_dir()
    workspace.mkdir(parents=True, exist_ok=True)
    return create_project("默认项目", str(workspace))


def get_project(project_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT p.*, COUNT(s.id) AS session_count, "
            "MAX(s.updated_at) AS last_activity "
            "FROM projects p LEFT JOIN sessions s ON s.project_id = p.id "
            "GROUP BY p.id ORDER BY p.updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def update_project(
    project_id: str,
    name: str | None = None,
    path: str | None = None,
    icon: str | None = None,
) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise KeyError(project_id)
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE projects SET name = ?, path = ?, icon = ?, updated_at = ? "
            "WHERE id = ?",
            (
                name if name is not None else project["name"],
                path if path is not None else project["path"],
                icon if icon is not None else project.get("icon", "folder"),
                _now(),
                project_id,
            ),
        )
        conn.commit()
    return get_project(project_id)


def delete_project(project_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def session_workspace(session_id: str) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT p.path FROM sessions s "
            "JOIN projects p ON p.id = s.project_id "
            "WHERE s.id = ?",
            (session_id,),
        ).fetchone()
    return str(row["path"]) if row else None


def create_session(
    title: str | None = None,
    project_id: str | None = None,
    approval_mode: str | None = None,
) -> dict[str, Any]:
    session_id = _new_id()
    now = _now()
    if not project_id:
        project_id = default_project()["id"]
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(id, title, project_id, approval_mode, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                title or "新对话",
                project_id,
                approval_mode or "ask",
                now,
                now,
            ),
        )
        conn.commit()
    return get_session(session_id)


def get_session(session_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_sessions(project_id: str | None = None) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE project_id = ? "
                "ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def update_session(
    session_id: str,
    title: str | None = None,
    approval_mode: str | None = None,
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, approval_mode = ?, updated_at = ? "
            "WHERE id = ?",
            (
                title if title is not None else session["title"],
                approval_mode if approval_mode is not None else session["approval_mode"],
                _now(),
                session_id,
            ),
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
        conn.execute("DELETE FROM agent_todos WHERE session_id = ?", (session_id,))
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


def save_tool_turn(
    session_id: str,
    tool_calls: list[dict[str, Any]],
    think: str,
    results: list[tuple[str, str]],
) -> None:
    if not tool_calls:
        return
    message = add_message(session_id, "assistant", "")
    order = 0
    add_message_part(
        message["id"],
        "tool_calls",
        json.dumps(tool_calls, ensure_ascii=False),
        order=order,
    )
    order += 1
    if think:
        add_message_part(message["id"], "think", think, order=order)
        order += 1
    for call_id, content in results:
        tool_message = add_message(session_id, "tool", content)
        add_message_part(
            tool_message["id"],
            "tool_result",
            json.dumps({"tool_call_id": call_id}, ensure_ascii=False),
            order=0,
        )


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


def replace_todos(
    session_id: str, titles: list[str]
) -> list[dict[str, Any]]:
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "DELETE FROM agent_todos WHERE session_id = ?", (session_id,)
        )
        for index, title in enumerate(titles):
            conn.execute(
                "INSERT INTO agent_todos "
                "(id, session_id, \"index\", title, status, result, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
                (_new_id(), session_id, index, title, now, now),
            )
        conn.commit()
    return list_todos(session_id)


def list_todos(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM agent_todos WHERE session_id = ? "
            "ORDER BY \"index\" ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_todo_status(
    todo_id: str, status: str, result: str | None = None
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE agent_todos SET status = ?, result = ?, updated_at = ? "
            "WHERE id = ?",
            (status, result, _now(), todo_id),
        )
        conn.commit()


def history_for_model(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Model-facing history; file attachments are rehydrated into user turns."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
        messages = [dict(row) for row in rows][-limit:]
        parts_by_message: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if messages:
            ids = [message["id"] for message in messages]
            placeholders = ",".join("?" * len(ids))
            part_rows = conn.execute(
                f"SELECT * FROM message_parts WHERE message_id IN ({placeholders}) "
                "ORDER BY \"order\" ASC, rowid ASC",
                ids,
            ).fetchall()
            for row in part_rows:
                parts_by_message[row["message_id"]].append(dict(row))

    while messages and messages[0]["role"] == "tool":
        messages.pop(0)

    result: list[dict[str, Any]] = []
    pending_tool_call_ids: set[str] = set()
    for message in messages:
        parts = parts_by_message.get(message["id"], [])
        content = message["content"]
        if message["role"] == "user":
            blocks: list[str] = []
            for part in parts:
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
            pending_tool_call_ids = set()
            result.append({"role": "user", "content": content})
            continue
        if message["role"] == "assistant":
            think_parts = [
                part["content"] for part in parts if part["type"] == "think"
            ]
            tool_calls_part = next(
                (part for part in parts if part["type"] == "tool_calls"),
                None,
            )
            if tool_calls_part is not None:
                try:
                    tool_calls = json.loads(tool_calls_part["content"] or "[]")
                except json.JSONDecodeError:
                    tool_calls = []
                if not tool_calls:
                    result.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "reasoning_content": "\n".join(think_parts),
                        }
                    )
                    continue
                result.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls,
                        "reasoning_content": "\n".join(think_parts),
                    }
                )
                pending_tool_call_ids = {
                    call.get("id", "") for call in tool_calls if call.get("id")
                }
                continue
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "reasoning_content": "\n".join(think_parts),
            }
            result.append(entry)
            continue
        if message["role"] == "tool":
            call_id = ""
            for part in parts:
                if part["type"] != "tool_result":
                    continue
                try:
                    call_id = str(
                        json.loads(part["content"]).get("tool_call_id", "")
                    )
                except (json.JSONDecodeError, AttributeError):
                    call_id = ""
            if call_id not in pending_tool_call_ids:
                continue
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content,
                }
            )
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
        "todos": list_todos(session_id),
    }
