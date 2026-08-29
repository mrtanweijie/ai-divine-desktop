from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from pathlib import Path

from .db.connection import get_conn

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
MAX_FILES = 500
MAX_CHUNK_CHARS = 1000

_RAG_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_chunks (
    workspace_key TEXT NOT NULL,
    chunk_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    tokens TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_terms (
    workspace_key TEXT NOT NULL,
    term TEXT NOT NULL,
    doc_freq INTEGER NOT NULL,
    PRIMARY KEY (workspace_key, term)
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_key
    ON rag_chunks(workspace_key);
"""

_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema() -> None:
    """Create RAG tables once on the shared connection (idempotent)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = get_conn()
        conn.executescript(_RAG_SCHEMA)
        conn.commit()
        _schema_ready = True


def _connect() -> sqlite3.Connection:
    """Return the shared per-thread connection with the RAG schema ensured."""
    _ensure_schema()
    return get_conn()


def workspace_key(workspace: Path) -> str:
    return hashlib.sha256(
        str(workspace.resolve()).encode("utf-8")
    ).hexdigest()[:16]


def tokenize(text: str) -> list[str]:
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


def _chunk_text(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [
        normalized[start : start + MAX_CHUNK_CHARS]
        for start in range(0, len(normalized), MAX_CHUNK_CHARS)
    ]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _collect_files(workspace: Path, extra_path: str = "") -> list[Path]:
    base = workspace
    if extra_path:
        candidate = Path(extra_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
        try:
            base.relative_to(workspace.resolve())
        except ValueError:
            return []
    if not base.is_dir():
        return []
    files: list[Path] = []
    for root, dirs, names in os.walk(base):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and d != "node_modules"
        )
        for name in sorted(names):
            if name.startswith("."):
                continue
            if Path(name).suffix.lower() not in (".txt", ".md", ".csv", ".json"):
                continue
            files.append(Path(root) / name)
            if len(files) >= MAX_FILES:
                return files
    return files


def index_workspace(
    workspace: Path, extra_path: str = ""
) -> dict[str, int]:
    files = _collect_files(workspace, extra_path)
    key = workspace_key(workspace)
    with _connect() as conn:
        conn.execute("DELETE FROM rag_chunks WHERE workspace_key = ?", (key,))
        conn.execute("DELETE FROM rag_terms WHERE workspace_key = ?", (key,))
        doc_freq: dict[str, int] = {}
        chunk_count = 0
        for file_path in files:
            try:
                text = _read_text(file_path)[:200_000]
            except OSError:
                continue
            for chunk_index, chunk in enumerate(_chunk_text(text)):
                tokens = _term_frequency(tokenize(chunk))
                if not tokens:
                    continue
                chunk_id = f"{key}:{chunk_count}"
                conn.execute(
                    "INSERT INTO rag_chunks "
                    "(workspace_key, chunk_id, file_path, chunk_index, text, tokens) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        chunk_id,
                        str(file_path),
                        chunk_index,
                        chunk,
                        json.dumps(tokens, ensure_ascii=False),
                    ),
                )
                chunk_count += 1
                for term in tokens:
                    doc_freq[term] = doc_freq.get(term, 0) + 1
        conn.executemany(
            "INSERT OR REPLACE INTO rag_terms "
            "(workspace_key, term, doc_freq) VALUES (?, ?, ?)",
            [(key, term, count) for term, count in doc_freq.items()],
        )
        conn.commit()
    return {"files": len(files), "chunks": chunk_count}


def search_workspace(
    workspace: Path, query: str, top_k: int = 5
) -> list[dict[str, object]]:
    key = workspace_key(workspace)
    with _connect() as conn:
        chunks = conn.execute(
            "SELECT chunk_id, file_path, chunk_index, text, tokens "
            "FROM rag_chunks WHERE workspace_key = ?",
            (key,),
        ).fetchall()
        if not chunks:
            return []
        term_rows = conn.execute(
            "SELECT term, doc_freq FROM rag_terms WHERE workspace_key = ?",
            (key,),
        ).fetchall()
    idf = {
        term: math.log((len(chunks) + 1) / (doc_freq + 1)) + 1
        for term, doc_freq in term_rows
    }
    query_tokens = _term_frequency(tokenize(query))
    query_vector = {
        term: count * idf.get(term, 1.0)
        for term, count in query_tokens.items()
    }
    if not query_vector:
        return []
    query_norm = math.sqrt(
        sum(value * value for value in query_vector.values())
    )
    results: list[tuple[float, str, int, str]] = []
    for chunk in chunks:
        _, file_path, chunk_index, text, tokens_json = chunk
        tokens = json.loads(tokens_json)
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
            results.append((score, file_path, chunk_index, text[:1500]))
    results.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": round(score, 4),
            "file_path": file_path,
            "chunk_index": chunk_index,
            "snippet": snippet,
        }
        for score, file_path, chunk_index, snippet in results[: max(1, top_k)]
    ]
