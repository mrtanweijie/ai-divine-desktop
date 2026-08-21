"""Schema definition and startup migration logic."""

from __future__ import annotations

from contextlib import closing

from .connection import _connect
from .projects import default_project

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
    plan_mode TEXT NOT NULL DEFAULT 'ask',
    locale TEXT NOT NULL DEFAULT 'zh-CN',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    choice_state TEXT NOT NULL DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL DEFAULT 'reminder',
    frequency TEXT NOT NULL DEFAULT 'interval',
    interval_minutes INTEGER,
    run_at TEXT,
    run_hour INTEGER,
    run_minute INTEGER,
    days_of_week TEXT NOT NULL DEFAULT '[]',
    day_of_month INTEGER,
    next_run_at TEXT,
    last_run_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    calendar_synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT,
    notes TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    task_id TEXT REFERENCES scheduled_tasks(id) ON DELETE SET NULL,
    system_event_id TEXT,
    synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_parts_message ON message_parts(message_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_session ON tool_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_todos_session ON agent_todos(session_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status ON scheduled_tasks(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_session ON scheduled_tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_task ON calendar_events(task_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_at);

CREATE TABLE IF NOT EXISTS user_memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.8,
    status TEXT NOT NULL DEFAULT 'active',
    source_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    superseded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_status ON user_memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_category ON user_memories(category);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    summary TEXT NOT NULL DEFAULT '',
    cutoff_rowid INTEGER NOT NULL DEFAULT 0,
    saved_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

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
        if "plan_mode" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN plan_mode TEXT "
                "NOT NULL DEFAULT 'ask'"
            )
        if "locale" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN locale TEXT "
                "NOT NULL DEFAULT 'zh-CN'"
            )
        message_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(messages)")
        }
        if "choice_state" not in message_columns:
            conn.execute(
                "ALTER TABLE messages ADD COLUMN choice_state TEXT "
                "NOT NULL DEFAULT '{}'"
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
