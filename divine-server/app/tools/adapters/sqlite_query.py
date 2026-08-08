from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, resolve_external_path
from ..registry import register_tool


@register_tool(
    "sqlite_query",
    "以只读方式查询本地 SQLite 数据库，只允许 SELECT/PRAGMA/EXPLAIN/WITH，返回查询结果",
    {
        "type": "object",
        "properties": {
            "db_path": {"type": "string", "description": "SQLite 数据库文件路径"},
            "query": {"type": "string", "description": "只读 SQL 查询语句"},
        },
        "required": ["db_path", "query"],
    },
)
class SqliteQueryAdapter(ToolAdapter):
    script_name = "sqlite_query.py"
    category = "files"
    timeout = 20
    allow_external_paths = True

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "db_path": str(arguments.get("db_path") or ""),
            "query": str(arguments.get("query") or ""),
        }

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(workspace, arguments.get("db_path"))
        return [external] if external else []
