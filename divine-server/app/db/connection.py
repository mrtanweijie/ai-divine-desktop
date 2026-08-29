"""Low-level SQLite connection and shared serialization helpers.

Connections are cached per-thread (``threading.local``) so hot-path
repositories reuse a single open connection instead of opening/closing a file
handle on every call. The cache is keyed by the resolved DB path, so tests or
runtimes that change ``DB_PATH`` transparently get a fresh connection.

Usage::

    from .connection import get_conn

    with get_conn() as conn:          # commits on success, rolls back on error
        conn.execute("...")
        conn.commit()

The connection is *not* closed when the ``with`` block exits — it is returned
to the calling thread's cache. Call :func:`close_thread_conn` to release a
thread's connection (e.g. on shutdown or after the DB file path changes).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import db_path

_local = threading.local()


def _connect() -> sqlite3.Connection:
    """Open a fresh connection (used on cache miss and by tests)."""
    conn = sqlite3.connect(db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_conn() -> sqlite3.Connection:
    """Return the calling thread's cached connection, creating it on first use.

    If ``db_path()`` has changed since the connection was created (tests set
    ``DB_PATH`` per test), the stale connection is closed and a new one opened
    for the current path.
    """
    path = str(db_path())
    cached = getattr(_local, "conn", None)
    if cached is not None and cached[0] == path:
        return cached[1]
    if cached is not None:
        try:
            cached[1].close()
        except sqlite3.Error:
            pass
    conn = _connect()
    _local.conn = (path, conn)
    return conn


def close_thread_conn() -> None:
    """Close and drop the calling thread's cached connection."""
    cached = getattr(_local, "conn", None)
    _local.conn = None
    if cached is not None:
        try:
            cached[1].close()
        except sqlite3.Error:
            pass


def _new_id() -> str:
    return uuid.uuid4().hex

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
