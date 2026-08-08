from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path


def _cell(value) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    return text[:2000]


def _validate_query(query: str) -> str:
    core = query.strip().rstrip(";").strip()
    if not core:
        raise ValueError("查询语句不能为空")
    if ";" in core:
        raise ValueError("只允许单条查询语句")
    lowered = core.lower()
    if not lowered.startswith(("select", "pragma", "explain", "with")):
        raise ValueError("只允许 SELECT/PRAGMA/EXPLAIN/WITH 查询")
    if re.search(r"\b(attach|load_extension)\b", lowered):
        raise ValueError("不允许 ATTACH 或 LOAD_EXTENSION")
    return core


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    raw = str(params.get("db_path") or "").strip()
    if not raw:
        print(json.dumps({"success": False, "message": "缺少 db_path"}))
        return
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.is_file():
        print(json.dumps({"success": False, "message": f"数据库不存在: {path}"}))
        return
    query = str(params.get("query") or "")
    try:
        query = _validate_query(query)
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query)
            columns = [item[0] for item in cursor.description or []]
            data_rows = [
                [_cell(value) for value in row]
                for row in cursor.fetchmany(200)
            ]
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"查询失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {
                "success": True,
                "message": f"查询完成，返回 {len(data_rows)} 行",
                "content": json.dumps(
                    {"columns": columns, "rows": data_rows},
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
