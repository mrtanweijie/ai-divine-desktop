"""Low-level SQLite connection and shared serialization helpers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from ..config import db_path

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _new_id() -> str:
    return uuid.uuid4().hex

def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
