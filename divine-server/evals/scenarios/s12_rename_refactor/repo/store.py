"""数据存取层。"""

_DB: dict[str, list[dict]] = {
    "users": [{"id": 1, "name": "Ann"}, {"id": 2, "name": "Bob"}],
    "logs": [{"id": 1, "msg": "boot"}],
}


def fetch_data(table: str) -> list[dict]:
    """Return a copy of all rows of a table."""
    return [dict(row) for row in _DB.get(table, [])]


def table_names() -> list[str]:
    return sorted(_DB)
