"""Long-term user memory repository.

Memories are lightweight, single-user, SQLite-persisted preference/fact
entries that outlive any single session. Retrieval reuses the local
tokenize + TF-IDF + cosine scoring approach from ``app.rag_store`` so no
embedding model or FTS5 dependency is required.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .connection import get_conn, _new_id, _now

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_ACTIVE = "active"
_SUPERSEDED = "superseded"

# Soft-deletion keeps audit history; only active rows are returned by default.
_ALLOWED_CATEGORIES = ("preference", "fact", "event")


def _tokenize(text: str) -> list[str]:
    words = [word.lower() for word in _TOKEN_RE.findall(text)]
    cjk_chars = _CJK_RE.findall(text)
    bigrams = [
        cjk_chars[index] + cjk_chars[index + 1]
        for index in range(len(cjk_chars) - 1)
    ]
    return words + cjk_chars + bigrams


def _term_frequency(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def save_memory(
    content: str,
    category: str = "preference",
    importance: float = 0.5,
    confidence: float = 0.8,
    source_session_id: str | None = None,
    supersede_similar: bool = True,
) -> dict[str, Any]:
    """Insert one memory, optionally superseding similar active entries.

    Superseding is a cheap token-overlap guard against duplicates (e.g. the
    user states a preference, later corrects it). Exact text and high-overlap
    active rows in the same category are marked ``superseded``.
    """
    content = str(content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    if category not in _ALLOWED_CATEGORIES:
        raise ValueError(f"category 必须是 {_ALLOWED_CATEGORIES} 之一")
    importance = max(0.0, min(1.0, float(importance or 0.5)))
    confidence = max(0.0, min(1.0, float(confidence or 0.8)))
    now = _now()
    memory_id = _new_id()

    with get_conn() as conn:
        if supersede_similar:
            query_tokens = set(_tokenize(content))
            rows = conn.execute(
                "SELECT * FROM user_memories "
                "WHERE status = ? AND category = ?",
                (_ACTIVE, category),
            ).fetchall()
            for row in rows:
                existing = _row_to_dict(row)
                existing_tokens = set(_tokenize(existing["content"]))
                if not existing_tokens:
                    continue
                union = query_tokens | existing_tokens
                jaccard = len(query_tokens & existing_tokens) / len(union)
                is_subset = existing_tokens <= query_tokens and len(
                    existing_tokens
                ) <= len(query_tokens)
                if is_subset or jaccard >= 0.5:
                    conn.execute(
                        "UPDATE user_memories SET status = ?, superseded_at = ? "
                        "WHERE id = ?",
                        (_SUPERSEDED, now, existing["id"]),
                    )
        conn.execute(
            "INSERT INTO user_memories "
            "(id, category, content, importance, confidence, status, "
            " source_session_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory_id,
                category,
                content,
                importance,
                confidence,
                _ACTIVE,
                source_session_id,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_memories WHERE id = ?", (memory_id,)
        ).fetchone()
    return _row_to_dict(row)


def list_active_memories(
    category: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return active memories, newest first, optionally filtered by category."""
    with get_conn() as conn:
        if category and category in _ALLOWED_CATEGORIES:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? AND category = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (_ACTIVE, category, max(1, int(limit))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (_ACTIVE, max(1, int(limit))),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_memories(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Rank active memories against a query with local TF-IDF cosine scoring.

    Mirrors ``app.rag_store.search_workspace`` so results are comparable and
    cost zero external calls. Falls back to newest-first when the query has
    no tokenizable content.
    """
    memories = list_active_memories(limit=500)
    if not memories:
        return []
    query_tokens = _term_frequency(_tokenize(query or ""))
    if not query_tokens:
        return memories[: max(1, limit)]

    doc_freq: dict[str, int] = {}
    for memory in memories:
        for token in set(_tokenize(memory["content"])):
            doc_freq[token] = doc_freq.get(token, 0) + 1
    total = len(memories)
    idf = {
        term: math.log((total + 1) / (freq + 1)) + 1
        for term, freq in doc_freq.items()
    }
    query_vector = {
        term: count * idf.get(term, 1.0)
        for term, count in query_tokens.items()
    }
    query_norm = math.sqrt(
        sum(value * value for value in query_vector.values())
    )

    results: list[tuple[float, dict[str, Any]]] = []
    for memory in memories:
        tokens = _term_frequency(_tokenize(memory["content"]))
        dot = 0.0
        norm = 0.0
        for term, count in tokens.items():
            weight = count * idf.get(term, 0.0)
            norm += weight * weight
            if term in query_vector:
                dot += query_vector[term] * weight
        if norm <= 0 or query_norm <= 0:
            continue
        score = dot / (math.sqrt(norm) * query_norm)
        if score > 0:
            results.append((score, memory))
    results.sort(key=lambda item: item[0], reverse=True)
    return [
        dict(memory, score=round(score, 4))
        for score, memory in results[: max(1, limit)]
    ]


def forget_memory(memory_id: str) -> bool:
    """Soft-delete one memory; returns True when an active row was removed."""
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE user_memories SET status = ?, superseded_at = ? "
            "WHERE id = ? AND status = ?",
            (_SUPERSEDED, _now(), memory_id, _ACTIVE),
        )
        conn.commit()
        return cursor.rowcount > 0


def forget_memory_by_content(content: str) -> int:
    """Soft-delete active memories whose content matches exactly (trimmed).

    Used by the forget_memory tool when the LLM only recalls the wording.
    Returns the number of removed rows.
    """
    content = str(content or "").strip()
    if not content:
        return 0
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE user_memories SET status = ?, superseded_at = ? "
            "WHERE status = ? AND trim(content) = ?",
            (_SUPERSEDED, _now(), _ACTIVE, content),
        )
        conn.commit()
        return cursor.rowcount
