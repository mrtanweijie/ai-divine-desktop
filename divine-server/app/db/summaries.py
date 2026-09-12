"""Session summary repository (context compaction state).

Design 022 升级：摘要是 L1 情景记忆的载体——除同会话续接外，还通过
``search_summaries`` 支持跨会话检索（``recall_memories`` 工具的
``scope=session``）。``project_id`` 从 sessions 冗余写入，检索免 join。
"""

from __future__ import annotations

from typing import Any

from .connection import get_conn, _now
from .retrieval import rank_documents

def get_summary(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None

def save_summary(
    session_id: str,
    summary: str,
    cutoff_rowid: int,
    saved_tokens: int = 0,
) -> dict[str, Any]:
    now = _now()
    with get_conn() as conn:
        project_id = conn.execute(
            "SELECT project_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        project_id = (
            str(project_id["project_id"]) if project_id else None
        )
        conn.execute(
            "INSERT INTO session_summaries "
            "(session_id, summary, cutoff_rowid, saved_tokens, project_id, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "summary = excluded.summary, "
            "cutoff_rowid = excluded.cutoff_rowid, "
            "saved_tokens = excluded.saved_tokens, "
            "project_id = excluded.project_id, "
            "updated_at = excluded.updated_at",
            (
                session_id,
                summary,
                int(cutoff_rowid),
                int(saved_tokens),
                project_id,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row)

def delete_summary(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM session_summaries WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()


def search_summaries(
    query: str,
    limit: int = 5,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Cross-session retrieval over summary full texts (local TF-IDF).

    给定 ``project_id`` 时只返回该项目的会话摘要；未给定时返回全部
    （单用户产品，会话本身即用户作用域）。摘要只有几百字，直接对全文
    跑 rank_documents，无需关键词列（022 §4.3 v2 简化）。
    """
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM session_summaries WHERE project_id = ? "
                "ORDER BY updated_at DESC LIMIT 500",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM session_summaries "
                "ORDER BY updated_at DESC LIMIT 500"
            ).fetchall()
    docs = [str(row["summary"] or "") for row in rows]
    ranked = rank_documents(query, docs, top_k=max(1, limit))
    results: list[dict[str, Any]] = []
    for score, index in ranked:
        if score <= 0:
            continue
        row = dict(rows[index])
        row["id"] = row["session_id"]
        row["category"] = "session"
        row["content"] = row["summary"]
        row["score"] = round(score, 4)
        results.append(row)
    return results
