"""Project repository."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from ..config import workspace_dir
from .connection import _connect, _new_id, _now

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
