"""Long-term user memory repository.

Memories are lightweight, single-user, SQLite-persisted preference/fact
entries that outlive any single session. Retrieval reuses the shared local
tokenize + TF-IDF + cosine scoring primitives from ``app.db.retrieval`` so
no embedding model or FTS5 dependency is required.

Status machine (see docs/design/022-agent-memory-architecture-20260911.md):

- ``active``    — injected / retrievable;
- ``pending``   — conflict gray zone (polarity clash with a similar old
  memory): kept out of read paths until a human confirms or rejects it;
- ``superseded``— soft-deleted / overridden; ``superseded_by`` records the
  overriding memory id (or the ``supersede_id`` the model passed) so every
  override is traceable and restorable.

Design principle: every conflict heuristic can misfire, so its failure mode
must be benign — keep both rows or park the new one as ``pending``, never
silently drop a contradicting memory.
"""

from __future__ import annotations

import math
from typing import Any

from .connection import get_conn, _new_id, _now
from .retrieval import term_frequency as _term_frequency
from .retrieval import tokenize as _tokenize

_ACTIVE = "active"
_PENDING = "pending"
_SUPERSEDED = "superseded"
_ALLOWED_STATUSES = (_ACTIVE, _PENDING)

# Soft-deletion keeps audit history; only active rows are returned by default.
_ALLOWED_CATEGORIES = ("preference", "fact", "event")

# 极性闸门：命中任一提示词视为负极性。子串匹配必然误判，所以它只决定
# 「冲突时新记忆是否挂起」，永不直接触发删除（原则 5：失败模式良性）。
_NEGATION_HINTS = ("不", "没", "无", "别", "禁止", "拒绝", "讨厌", "不用", "不再是")
# 含否定字但不表达否定的常见词，先摘除再匹配，降低误判面。
_NEGATION_FALSE_POSITIVES = (
    "不错",
    "无比",
    "别提",
    "毫无压力",
    "不亦乐乎",
    "无非",
    "不凡",
    "不耻",
)

# 自动 supersede 只防高重复，不处理语义变化（改述式更新走 supersede_id）。
_AUTO_SUPERSEDE_JACCARD = 0.85
# 低于此相似度视为不同话题，无论极性如何都各自独立存活。
_CONFLICT_JACCARD = 0.5
# 子集判定的护栏：新旧 token 数差 ≤ 2 且长度比落在该区间才允许吞并，
# 避免短句吞掉长句。
_SUBSET_TOKEN_DIFF = 2
_LENGTH_RATIO_RANGE = (0.6, 1.7)


def _polarity(content: str) -> int:
    text = str(content or "")
    for phrase in _NEGATION_FALSE_POSITIVES:
        text = text.replace(phrase, "")
    return -1 if any(hint in text for hint in _NEGATION_HINTS) else 1


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _supersede(
    conn: Any, memory_id: str, superseded_by: str | None, now: str
) -> None:
    conn.execute(
        "UPDATE user_memories SET status = ?, superseded_at = ?, "
        "superseded_by = ? WHERE id = ?",
        (_SUPERSEDED, now, superseded_by, memory_id),
    )


def save_memory(
    content: str,
    category: str = "preference",
    importance: float = 0.5,
    confidence: float = 0.8,
    source_session_id: str | None = None,
    supersede_similar: bool = True,
    supersede_id: str | None = None,
    status: str = _ACTIVE,
) -> dict[str, Any]:
    """Insert one memory, handling overlap with existing active entries.

    ``supersede_id`` — explicit override requested by the model: the named
    active memory is superseded regardless of similarity thresholds. This is
    the sanctioned path for paraphrased updates ("以前喜欢 Python，现在主用
    Go 了"), which no token-overlap heuristic can catch.

    Without it, auto-superseding is deliberately narrow: only near-exact
    duplicates (jaccard >= 0.85, or a guarded subset) with the same polarity
    are replaced. A similar old memory with the *opposite* polarity puts the
    new row into ``pending`` instead — both survive, a human decides.
    """
    content = str(content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    if category not in _ALLOWED_CATEGORIES:
        raise ValueError(f"category 必须是 {_ALLOWED_CATEGORIES} 之一")
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"status 必须是 {_ALLOWED_STATUSES} 之一")
    importance = max(0.0, min(1.0, float(importance or 0.5)))
    confidence = max(0.0, min(1.0, float(confidence or 0.8)))
    supersede_id = str(supersede_id or "").strip() or None
    now = _now()
    memory_id = _new_id()

    with get_conn() as conn:
        if supersede_id:
            old = conn.execute(
                "SELECT status FROM user_memories WHERE id = ?",
                (supersede_id,),
            ).fetchone()
            if old is None or old["status"] != _ACTIVE:
                raise ValueError("要覆盖的旧记忆不存在或已失效")

        final_status = status
        if supersede_similar and not supersede_id and status == _ACTIVE:
            query_tokens = set(_tokenize(content))
            query_polarity = _polarity(content)
            query_length = len(content)
            rows = conn.execute(
                "SELECT * FROM user_memories "
                "WHERE status = ? AND category = ?",
                (_ACTIVE, category),
            ).fetchall()
            for row in rows:
                existing = _row_to_dict(row)
                existing_content = str(existing["content"] or "")
                existing_tokens = set(_tokenize(existing_content))
                if not existing_tokens or not query_tokens:
                    continue
                union = query_tokens | existing_tokens
                jaccard = len(query_tokens & existing_tokens) / len(union)
                if jaccard < _CONFLICT_JACCARD:
                    continue
                is_subset = (
                    existing_tokens <= query_tokens
                    and len(existing_tokens) <= len(query_tokens)
                    and abs(len(query_tokens) - len(existing_tokens))
                    <= _SUBSET_TOKEN_DIFF
                )
                length_ratio = len(existing_content) / max(1, query_length)
                subset_guarded = (
                    is_subset
                    and _LENGTH_RATIO_RANGE[0]
                    <= length_ratio
                    <= _LENGTH_RATIO_RANGE[1]
                )
                same_polarity = _polarity(existing_content) == query_polarity
                if same_polarity and (
                    jaccard >= _AUTO_SUPERSEDE_JACCARD or subset_guarded
                ):
                    _supersede(conn, existing["id"], memory_id, now)
                elif not same_polarity:
                    # 极性相反的相似记忆：不覆盖任何一方，新记忆挂起待确认。
                    final_status = _PENDING
        conn.execute(
            "INSERT INTO user_memories "
            "(id, category, content, importance, confidence, status, "
            " source_session_id, created_at, updated_at, superseded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                memory_id,
                category,
                content,
                importance,
                confidence,
                final_status,
                source_session_id,
                now,
                now,
            ),
        )
        if supersede_id and final_status != _PENDING:
            _supersede(conn, supersede_id, memory_id, now)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_memories WHERE id = ?", (memory_id,)
        ).fetchone()
    return _row_to_dict(row)


def list_memories(
    status: str = _ACTIVE, category: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return memories filtered by status, newest first."""
    if status not in (_ACTIVE, _PENDING, _SUPERSEDED):
        raise ValueError(f"status 必须是 {_ACTIVE}/{_PENDING}/{_SUPERSEDED}")
    with get_conn() as conn:
        if category and category in _ALLOWED_CATEGORIES:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? AND category = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (status, category, max(1, int(limit))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (status, max(1, int(limit))),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_active_memories(
    category: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return active memories, newest first, optionally filtered by category."""
    return list_memories(status=_ACTIVE, category=category, limit=limit)


def list_pending_memories(limit: int = 50) -> list[dict[str, Any]]:
    """Return memories parked in the conflict gray zone, awaiting review."""
    return list_memories(status=_PENDING, limit=limit)


def confirm_pending_memory(memory_id: str) -> bool:
    """Promote a pending memory to active; returns True when it existed."""
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE user_memories SET status = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (_ACTIVE, _now(), memory_id, _PENDING),
        )
        conn.commit()
        return cursor.rowcount > 0


def reject_pending_memory(memory_id: str) -> bool:
    """Drop a pending memory (soft, keeps audit trail); True when it existed."""
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE user_memories SET status = ?, superseded_at = ? "
            "WHERE id = ? AND status = ?",
            (_SUPERSEDED, _now(), memory_id, _PENDING),
        )
        conn.commit()
        return cursor.rowcount > 0


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
