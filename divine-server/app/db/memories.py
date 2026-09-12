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
from datetime import datetime, timezone
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

# 打分权重（022 §4.2）：final = w_sim*sim_norm + 0.15*importance
#                            + 0.05*confidence + w_recency*recency
# sim_norm 是候选集内相对值（sim/max_sim），消除 TF-IDF 余弦与 [0,1]
# 标量之间的量纲差；w_sim = 1 - 0.15 - 0.05 - w_recency 恒闭合。
_WEIGHT_IMPORTANCE = 0.15
_WEIGHT_CONFIDENCE = 0.05
# category → (τ 天, w_recency)：偏好稳定几乎不衰减，事件时效性强。
_CATEGORY_RECENCY = {
    "preference": (180.0, 0.05),
    "fact": (90.0, 0.10),
    "event": (30.0, 0.20),
}
_RECENCY_DEFAULT = (180.0, 0.05)


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
    project_id: str | None = None,
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
            " source_session_id, created_at, updated_at, superseded_by, "
            " project_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
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
                project_id,
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


def _recency(memory: dict[str, Any]) -> float:
    """exp(-Δt/τ)，Δt 以 last_accessed_at 为基准（访问续命），无则回退
    updated_at；解析失败按刚访问处理（宁可不惩罚）。"""
    tau, _ = _CATEGORY_RECENCY.get(
        str(memory.get("category") or ""), _RECENCY_DEFAULT
    )
    base = (
        memory.get("last_accessed_at")
        or memory.get("updated_at")
        or memory.get("created_at")
    )
    try:
        accessed = datetime.fromisoformat(str(base))
        delta_days = max(
            0.0, (datetime.now(timezone.utc) - accessed).total_seconds() / 86400
        )
    except (TypeError, ValueError):
        delta_days = 0.0
    return math.exp(-delta_days / tau)


def _active_rows(
    project_id: str | None = None, search_all: bool = False
) -> list[dict[str, Any]]:
    """Load active memories for a retrieval scope.

    - ``search_all``  — everything (fuzzy delete 等管理动作需要跨作用域);
    - ``project_id``  — 该项目记忆 + 全局记忆（其他项目的记忆不可见）;
    - 否则            — 仅全局记忆（project_id IS NULL）。
    """
    with get_conn() as conn:
        if search_all:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT 500",
                (_ACTIVE,),
            ).fetchall()
        elif project_id:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? "
                "AND (project_id IS NULL OR project_id = ?) "
                "ORDER BY updated_at DESC, rowid DESC LIMIT 500",
                (_ACTIVE, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_memories WHERE status = ? "
                "AND project_id IS NULL "
                "ORDER BY updated_at DESC, rowid DESC LIMIT 500",
                (_ACTIVE,),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_memories(
    query: str,
    limit: int = 5,
    project_id: str | None = None,
    search_all: bool = False,
) -> list[dict[str, Any]]:
    """Rank active memories against a query with local TF-IDF cosine scoring.

    Mirrors ``app.rag_store.search_workspace`` so results are comparable and
    cost zero external calls. Falls back to newest-first when the query has
    no tokenizable content.

    Final ranking mixes the (relative-normalized) cosine with importance,
    confidence and recency — weights are closed over any w_recency, see the
    ``_CATEGORY_RECENCY`` table. Callers should :func:`touch_memory_access`
    the returned ids so hot memories keep their recency.

    项目作用域（022 §5.3）：给定 ``project_id`` 时项目记忆优先、全局记忆
    预留席位（若存在全局候选），其他项目的记忆一律不可见。
    """
    memories = _active_rows(project_id=project_id, search_all=search_all)
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

    sims: list[tuple[float, dict[str, Any]]] = []
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
            sims.append((score, memory))
    if not sims:
        return []

    max_sim = max(sim for sim, _ in sims) or 1.0
    scored: list[tuple[float, dict[str, Any], float]] = []
    for sim, memory in sims:
        _, w_recency = _CATEGORY_RECENCY.get(
            str(memory.get("category") or ""), _RECENCY_DEFAULT
        )
        w_sim = 1 - _WEIGHT_IMPORTANCE - _WEIGHT_CONFIDENCE - w_recency
        final = (
            w_sim * (sim / max_sim)
            + _WEIGHT_IMPORTANCE * float(memory.get("importance") or 0.5)
            + _WEIGHT_CONFIDENCE * float(memory.get("confidence") or 0.8)
            + w_recency * _recency(memory)
        )
        scored.append((final, memory, sim))
    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [
        dict(memory, score=round(final, 4), sim=round(sim, 4))
        for final, memory, sim in scored
    ]

    if not project_id:
        return ranked[: max(1, limit)]

    project_hits = [m for m in ranked if m.get("project_id") == project_id]
    global_hits = [m for m in ranked if not m.get("project_id")]
    # 项目记忆优先，但为全局记忆预留 2 席（若存在全局候选）——避免项目内
    # 记忆较多时把用户的通用偏好（饮食禁忌等）完全挤出注入面。
    global_reserve = 2 if global_hits else 0
    project_quota = max(1, limit - global_reserve)
    selected: list[dict[str, Any]] = project_hits[:project_quota]
    for hit in global_hits + project_hits[project_quota:]:
        if len(selected) >= limit:
            break
        if hit not in selected:
            selected.append(hit)
    return selected


def touch_memory_access(memory_ids: list[str]) -> None:
    """Record that memories were surfaced (injected or recalled).

    Recency is scored against ``last_accessed_at``, so regularly useful
    memories keep ranking instead of sinking with their write time.
    """
    ids = [mid for mid in memory_ids if mid]
    if not ids:
        return
    now = _now()
    with get_conn() as conn:
        conn.executemany(
            "UPDATE user_memories SET last_accessed_at = ? WHERE id = ?",
            [(now, memory_id) for memory_id in ids],
        )
        conn.commit()


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


# 模糊删除阈值（按真实语料实测标定，见 022 §5.2）：词汇余弦对无关记忆
# 也能冲到 0.3+（“用户在东京买房了” vs “用户在上海工作” = 0.34），单靠
# 绝对阈值会误删；自动删除要求 top1 足够高且显著领先 top2，其余一律
# 返回候选交由模型向用户确认——错问一次很便宜，错删一条不可逆。
_FORGET_AUTO_SIM = 0.45
_FORGET_DOMINANCE_GAP = 0.15
_FORGET_CANDIDATE_SIM = 0.12


def forget_memory_by_query(
    content: str,
    auto_score: float = _FORGET_AUTO_SIM,
    dominance_gap: float = _FORGET_DOMINANCE_GAP,
    candidate_score: float = _FORGET_CANDIDATE_SIM,
) -> dict[str, Any]:
    """Fuzzy delete: exact matches first, then retrieval-based matching.

    用户的口语化指认（"忘掉那条柯基的记忆"）几乎不可能精确命中，复用
    search_memories 做匹配：唯一高相似且显著领先的候选直接删；其余情况
    返回候选列表交由模型确认后按 id 删（原则 4：可纠正闭环，宁问勿删）。
    """
    content = str(content or "").strip()
    if not content:
        return {"exact_removed": 0, "deleted": [], "candidates": []}
    exact_removed = forget_memory_by_content(content)
    if exact_removed:
        return {
            "exact_removed": exact_removed,
            "deleted": [],
            "candidates": [],
        }
    hits = search_memories(content, limit=3, search_all=True)
    if hits:
        top = hits[0]
        second_sim = float(hits[1].get("sim") or 0.0) if len(hits) > 1 else 0.0
        top_sim = float(top.get("sim") or 0.0)
        if (
            top_sim >= auto_score
            and top_sim - second_sim >= dominance_gap
            and forget_memory(str(top["id"]))
        ):
            return {
                "exact_removed": 0,
                "deleted": [top],
                "candidates": [],
            }
    candidates = [
        hit
        for hit in hits
        if float(hit.get("sim") or 0.0) >= candidate_score
    ]
    return {"exact_removed": 0, "deleted": [], "candidates": candidates}


def recall_memories(
    query: str,
    scope: str = "user",
    limit: int = 5,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Unified recall entry for the ``recall_memories`` tool.

    scope=user 查全局记忆；scope=project 查项目记忆 + 全局合并（项目优先），
    scope=session 查历史会话结论（四期）。命中条目会刷新 last_accessed_at
    （访问续命）。
    """
    if scope == "session":
        # 四期接入 session_summaries 全文检索
        return []
    if scope == "project":
        hits = search_memories(query, limit=limit, project_id=project_id)
    else:
        hits = search_memories(query, limit=limit)
    if hits:
        now = _now()
        touch_memory_access([str(hit["id"]) for hit in hits])
        for hit in hits:
            hit["last_accessed_at"] = now
    return hits
