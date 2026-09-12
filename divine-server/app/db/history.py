"""Session history reconstruction for the model and the frontend."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from ..file_types import VISION_IMAGE_EXTENSIONS, is_image_path
from .connection import get_conn
from .messages import _attach_token_usage, _decode_choice_state, list_messages
from .sessions import get_session
from .todos import list_todos
from .tool_runs import list_message_parts, list_tool_runs

# Image links pasted by the user are fed to read_image (url param) so the
# vision model can analyze them. Only the formats the vision model supports
# (JPEG/PNG/GIF/WebP) are detected.
_VISION_EXT_ALT = "|".join(
    sorted(ext.lstrip(".") for ext in VISION_IMAGE_EXTENSIONS)
)
_IMAGE_URL_RE = re.compile(
    rf"https?://[^\s<>\"'()]+?\.(?:{_VISION_EXT_ALT})"
    r"(?:[?#][^\s<>\"'()]*)?",
    re.IGNORECASE,
)


def _image_urls_in(text: str) -> list[str]:
    return list(dict.fromkeys(_IMAGE_URL_RE.findall(text)))

def conn_summary(session_id: str) -> dict[str, Any] | None:
    """Session summary lookup independent of the caller's connection scope."""

    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None

def _fetch_window(
    conn,
    session_id: str,
    limit: int,
    until_message_id: str | None,
) -> list[dict[str, Any]]:
    """按模型上下文顺序取尾部消息窗口（升序返回）。

    复合键倒序取 limit 条再反转，与旧实现（升序全量加载后
    ``messages[-limit:]``）选中的行集逐条一致，但避免每轮全表解码。
    """
    params: list[Any] = [session_id]
    where = "session_id = ?"
    if until_message_id:
        target = conn.execute(
            "SELECT rowid FROM messages WHERE id = ? AND session_id = ?",
            (until_message_id, session_id),
        ).fetchone()
        # 目标不存在时与旧实现一致：不截断（旧的线性扫描同样查不到就整段返回）
        if target:
            where += " AND rowid <= ?"
            params.append(target["rowid"])
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM messages WHERE {where} "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def history_for_model(
    session_id: str,
    limit: int = 20,
    until_message_id: str | None = None,
) -> list[dict[str, Any]]:
    """Model-facing history; file attachments are rehydrated into user turns.

    When a session summary exists (context compaction), it is prepended as a
    synthetic system message so the model keeps early context without paying
    full token cost for every old message.

    ``until_message_id`` 指定时只取到该消息为止（含）——【重答云端】用：
    在目标用户问题处截断，丢弃其后（本地回答）的消息。
    """
    with get_conn() as conn:
        messages = _fetch_window(conn, session_id, limit, until_message_id)
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

    summary_row = conn_summary(session_id)

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
            image_urls = _image_urls_in(content)
            for url in image_urls:
                blocks.append(
                    f"[图片链接：{url}]\n"
                    "请调用 read_image 工具（url 参数）识别这张图片并分析内容，"
                    "再结合分析结果回答用户的问题。"
                )
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
    # 会话中断/工具执行失败会在历史里留下"assistant tool_calls 缺 tool 响应"
    # 的残缺组（例如并行调用只回了一部分）。OpenAI 兼容 API 对此返回 400
    # （assistant tool_calls 必须被 tool 消息逐条接续）。旧实现只清理尾部，
    # 但残缺组一旦被后续 user 消息顶到中段就会漏掉；改为全序列清洗：
    # 每条 assistant(tool_calls) 必须在遇到下一条非 tool 消息前被连续的
    # tool 消息覆盖全部 call id——未覆盖的 id 从 calls 剔除，剔除后既无
    # calls 也无 content 的 assistant 整条删除。让模型在下一轮重新规划
    # 而不是带着非法序列请求。
    result = _sanitize_tool_groups(result)
    if summary_row and summary_row.get("summary"):
        result.insert(
            0,
            {
                "role": "system",
                "content": (
                    "以下是本次会话早期对话的摘要（已压缩，帮助理解上下文）：\n"
                    f"{summary_row['summary']}"
                ),
            },
        )
    return result


def _sanitize_tool_groups(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Full-sequence orphan tool-call cleanup (mid-sequence and tail alike).

    OpenAI-compatible chat APIs validate that any ``assistant`` message
    carrying ``tool_calls`` is immediately followed by ``tool`` messages that
    respond to each ``tool_call_id`` — otherwise the whole request is rejected
    with 400. Interrupted/failed tool rounds (crash, cancel, timeout, an
    exception that ends the graph before tool results were written) leave
    orphan groups in the persisted history. The old tail-only cleanup missed
    groups that a later ``user`` message pushed into the middle of the
    sequence.

    Strategy per group (all-or-nothing): an ``assistant(tool_calls)`` group is
    kept only when the consecutive ``tool`` messages that follow it cover
    every call id; otherwise the assistant and its collected tool results are
    dropped together, letting the model re-plan cleanly next turn. Partial
    groups are NOT shrunk here on purpose — history assembly favors dropping
    half-finished tool rounds (the request-level sanitize in the LLM adapters
    is the place that keeps whatever is still valid). Unmatched tool messages
    (no pending group ahead) are dropped. Message order is preserved.
    """
    cleaned: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    pending_ids: set[str] = set()
    tools: list[dict[str, Any]] = []

    def settle() -> None:
        nonlocal pending, pending_ids, tools
        if pending is None:
            tools = []
            return
        group_call_ids = {
            str(call.get("id"))
            for call in pending.get("tool_calls") or []
            if isinstance(call, dict) and call.get("id")
        }
        # 仅保留归属于本组的 tool 结果：他组残留（脏数据）不参与配对。
        kept_tools = [
            tool
            for tool in tools
            if str(tool.get("tool_call_id") or "") in group_call_ids
        ]
        answered = {str(t.get("tool_call_id") or "") for t in kept_tools}
        if group_call_ids and group_call_ids <= answered:
            cleaned.append(pending)
            cleaned.extend(kept_tools)
        # 残缺组（含只回了部分 tool 的并行组）：整组丢弃，不残留孤儿消息。
        pending = None
        pending_ids = set()
        tools = []

    for message in messages:
        role = message.get("role")
        if role == "tool":
            if pending is not None:
                tools.append(message)
                cid = str(message.get("tool_call_id") or "")
                if cid in pending_ids:
                    pending_ids.discard(cid)
                continue
            # 无主 tool 消息（其 assistant 已被剔除/本就不完整）直接丢弃
            continue
        settle()
        if (
            role == "assistant"
            and message.get("tool_calls")
            and pending is None
        ):
            pending = message
            pending_ids = {
                str(call.get("id"))
                for call in message["tool_calls"]
                if isinstance(call, dict) and call.get("id")
            }
            tools = []
            continue
        cleaned.append(message)
    settle()
    return cleaned


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
    with get_conn() as conn:
        if before_id:
            rows = conn.execute(
                "SELECT m.*, m.rowid, u.input_tokens AS usage_input, "
                "u.output_tokens AS usage_output, u.total_tokens AS usage_total, "
                "u.source AS usage_source, u.created_at AS usage_created_at, "
                "u.duration_ms AS usage_duration_ms "
                "FROM messages m "
                "LEFT JOIN token_usage u ON u.message_id = m.id "
                "WHERE m.session_id = ? AND m.rowid < "
                "(SELECT rowid FROM messages WHERE id = ?) "
                "ORDER BY m.rowid DESC LIMIT ?",
                (session_id, before_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT m.*, m.rowid, u.input_tokens AS usage_input, "
                "u.output_tokens AS usage_output, u.total_tokens AS usage_total, "
                "u.source AS usage_source, u.created_at AS usage_created_at, "
                "u.duration_ms AS usage_duration_ms "
                "FROM messages m "
                "LEFT JOIN token_usage u ON u.message_id = m.id "
                "WHERE m.session_id = ? "
                "ORDER BY m.rowid DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        page = list(rows)[::-1]
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
        for row in page:
            item = dict(row)
            item.pop("rowid", None)
            message = _decode_choice_state(item)
            _attach_token_usage(message, row)
            messages.append(message)

    # Attach parts outside the connection scope: list_message_parts opens its
    # own get_conn() transaction on the shared connection, so calling it inside
    # the with block above would commit the outer (read-only) transaction.
    for message in messages:
        message["parts"] = list_message_parts(message["id"])

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
