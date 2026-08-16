"""Session history reconstruction for the model and the frontend."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import closing
from typing import Any

from ..file_types import is_image_path
from .connection import _connect
from .messages import _decode_choice_state, list_messages
from .sessions import get_session
from .todos import list_todos
from .tool_runs import list_message_parts, list_tool_runs

def history_for_model(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Model-facing history; file attachments are rehydrated into user turns."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
        messages = [dict(row) for row in rows][-limit:]
        parts_by_message: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if messages:
            ids = [message["id"] for message in messages]
            placeholders = ",".join("?" * len(ids))
            part_rows = conn.execute(
                f"SELECT * FROM message_parts WHERE message_id IN ({placeholders}) "
                "ORDER BY \"order\" ASC, rowid ASC",
                ids,
            ).fetchall()
            for row in part_rows:
                parts_by_message[row["message_id"]].append(dict(row))

    while messages and messages[0]["role"] == "tool":
        messages.pop(0)

    result: list[dict[str, Any]] = []
    pending_tool_call_ids: set[str] = set()
    for message in messages:
        parts = parts_by_message.get(message["id"], [])
        content = message["content"]
        if message["role"] == "user":
            blocks: list[str] = []
            for part in parts:
                if part["type"] != "file":
                    continue
                try:
                    meta = json.loads(part["content"])
                except json.JSONDecodeError:
                    meta = {"name": part["content"]}
                name = meta.get("name") or "附件"
                path = meta.get("path") or ""
                body = meta.get("content") or ""
                error = meta.get("error") or ""
                path_line = f"文件本地路径：{path}\n" if path else ""
                if path and is_image_path(path):
                    blocks.append(
                        f"[附件图片：{name}]\n图片本地路径：{path}\n"
                        "请调用 read_image 工具读取这张图片并分析内容，再结合分析结果回答用户的问题。"
                    )
                elif error:
                    if body:
                        blocks.append(
                            f"[附件：{name}]\n{path_line}读取失败: {error}\n"
                            "这不是图片文件，请直接分析以下内容，不要调用 read_image。\n"
                            f"```\n{body}\n```"
                        )
                    else:
                        blocks.append(
                            f"[附件：{name}]\n{path_line}读取失败: {error}"
                        )
                elif body:
                    blocks.append(
                        f"[附件：{name}]\n{path_line}"
                        "这不是图片文件，请直接分析以下内容，不要调用 read_image。\n"
                        f"```\n{body}\n```"
                    )
                else:
                    blocks.append(f"[附件：{name}]\n{path_line}".rstrip())
            if blocks:
                suffix = "\n\n".join(blocks)
                content = f"{content}\n\n{suffix}" if content else suffix
            pending_tool_call_ids = set()
            result.append({"role": "user", "content": content})
            continue
        if message["role"] == "assistant":
            think_parts = [
                part["content"] for part in parts if part["type"] == "think"
            ]
            tool_calls_part = next(
                (part for part in parts if part["type"] == "tool_calls"),
                None,
            )
            if tool_calls_part is not None:
                try:
                    tool_calls = json.loads(tool_calls_part["content"] or "[]")
                except json.JSONDecodeError:
                    tool_calls = []
                if not tool_calls:
                    if not content:
                        # 空回复（无内容且无工具调用）跳过，避免 API 400
                        continue
                    result.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "reasoning_content": "\n".join(think_parts),
                        }
                    )
                    continue
                result.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls,
                        "reasoning_content": "\n".join(think_parts),
                    }
                )
                pending_tool_call_ids = {
                    call.get("id", "") for call in tool_calls if call.get("id")
                }
                continue
            if not content:
                # 无内容、无工具调用的空 assistant 消息跳过
                continue
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "reasoning_content": "\n".join(think_parts),
            }
            result.append(entry)
            continue
        if message["role"] == "tool":
            call_id = ""
            for part in parts:
                if part["type"] != "tool_result":
                    continue
                try:
                    call_id = str(
                        json.loads(part["content"]).get("tool_call_id", "")
                    )
                except (json.JSONDecodeError, AttributeError):
                    call_id = ""
            if call_id not in pending_tool_call_ids:
                continue
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content,
                }
            )
            continue
        if content:
            result.append({"role": message["role"], "content": content})
    return result

def load_session(session_id: str) -> dict[str, Any]:
    """Full message view used by the frontend when restoring history."""
    messages = []
    for message in list_messages(session_id):
        messages.append(
            {
                **message,
                "parts": list_message_parts(message["id"]),
            }
        )
    return {
        "session": get_session(session_id),
        "messages": messages,
        "tool_runs": list_tool_runs(session_id),
        "todos": list_todos(session_id),
    }

def load_session_page(
    session_id: str,
    before_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Cursor-paginated message view for long conversation history."""
    limit = max(1, min(int(limit or 100), 200))
    with closing(_connect()) as conn:
        if before_id:
            rows = conn.execute(
                "SELECT *, rowid FROM messages "
                "WHERE session_id = ? AND rowid < "
                "(SELECT rowid FROM messages WHERE id = ?) "
                "ORDER BY rowid DESC LIMIT ?",
                (session_id, before_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT *, rowid FROM messages "
                "WHERE session_id = ? "
                "ORDER BY rowid DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        page = [dict(row) for row in rows][::-1]
        while page and page[0]["role"] != "user":
            page.pop(0)
        has_more = False
        if page:
            oldest_rowid = page[0]["rowid"]
            count = conn.execute(
                "SELECT COUNT(*) FROM messages "
                "WHERE session_id = ? AND rowid < ?",
                (session_id, oldest_rowid),
            ).fetchone()[0]
            has_more = count > 0
        messages = []
        for item in page:
            item.pop("rowid", None)
            messages.append(
                {
                    **_decode_choice_state(item),
                    "parts": list_message_parts(item["id"]),
                }
            )

    tool_runs = list_tool_runs(session_id)
    if messages:
        start = messages[0]["created_at"]
        end = messages[-1]["created_at"]
        tool_runs = [
            run
            for run in tool_runs
            if start <= run["started_at"] <= end
        ]

    return {
        "session": get_session(session_id),
        "messages": messages,
        "tool_runs": tool_runs,
        "todos": list_todos(session_id),
        "has_more": has_more,
    }
