"""Shared local retrieval primitives: tokenize + TF-IDF cosine scoring.

Extracted from ``app.db.memories`` so history backtracking (prompts) and
long-term memory retrieval share one implementation with zero external
dependencies (no embedding model / FTS5 required).
"""

from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """English words + CJK chars + CJK bigrams (no external deps)."""
    text = text or ""
    words = [word.lower() for word in _TOKEN_RE.findall(text)]
    cjk_chars = _CJK_RE.findall(text)
    bigrams = [
        cjk_chars[index] + cjk_chars[index + 1]
        for index in range(len(cjk_chars) - 1)
    ]
    return words + cjk_chars + bigrams


def term_frequency(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def rank_documents(
    query: str, docs: list[str], top_k: int = 3
) -> list[tuple[float, int]]:
    """Rank ``docs`` against ``query`` with local TF-IDF cosine scoring.

    Returns ``[(score, index), ...]`` sorted best-first, limited to ``top_k``.
    Empty query or all-zero vectors produce an empty result.
    """
    query_tokens = term_frequency(tokenize(query))
    if not query_tokens:
        return []
    total = len(docs)
    if total == 0:
        return []
    doc_tokens = [term_frequency(tokenize(doc)) for doc in docs]

    doc_freq: dict[str, int] = {}
    for tokens in doc_tokens:
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1
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
    if query_norm <= 0:
        return []

    scored: list[tuple[float, int]] = []
    for index, tokens in enumerate(doc_tokens):
        dot = 0.0
        norm = 0.0
        for term, count in tokens.items():
            weight = count * idf.get(term, 0.0)
            norm += weight * weight
            if term in query_vector:
                dot += query_vector[term] * weight
        if norm <= 0:
            continue
        score = dot / (math.sqrt(norm) * query_norm)
        if score > 0:
            scored.append((score, index))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[: max(1, top_k)]
