"""Persist LangGraph messages and tool turns into the SQLite session model."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from .. import db
from .schema import _content_text
from ..llm.think_tags import strip_think_tags

def _serialize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
        calls.append(
            {
                "id": call_id or "",
                "type": "function",
                "function": {
                    "name": name or "",
                    "arguments": json.dumps(args or {}, ensure_ascii=False),
                },
            }
        )
    return calls

def _persist_new_messages(
    session_id: str,
    input_messages: list[Any],
    messages: list[Any],
    think_by_id: dict[str, str],
) -> str | None:
    """Persist new AI/tool messages; return the id of the final assistant
    reply (or None when there is nothing to persist)."""
    last_input_index = -1
    if input_messages:
        last_input = input_messages[-1]
        for index, message in enumerate(messages):
            if type(message) is type(last_input) and _content_text(
                message.content
            ) == _content_text(last_input.content):
                last_input_index = index
    if last_input_index < 0:
        last_input_index = 0

    last_saved_id: str | None = None
    index = last_input_index + 1
    while index < len(messages):
        message = messages[index]
        if not isinstance(message, AIMessage):
            index += 1
            continue
        if message.tool_calls:
            calls = _serialize_tool_calls(message.tool_calls)
            results: list[tuple[str, str]] = []
            next_index = index + 1
            while next_index < len(messages) and isinstance(
                messages[next_index], ToolMessage
            ):
                results.append(
                    (
                        messages[next_index].tool_call_id,
                        _content_text(messages[next_index].content),
                    )
                )
                next_index += 1
            if results and len(results) >= len(calls):
                db.save_tool_turn(
                    session_id,
                    calls,
                    think_by_id.get(message.id, ""),
                    results,
                )
            index = next_index
            continue

        content = _content_text(message.content)
        if content:
            # 剥离推理模型内联的 <think> 块，只保存干净正文；
            # 思考内容单独经 think_by_id 存为 think 片段。
            content = strip_think_tags(content)
            if not content:
                index += 1
                continue
            saved = db.add_message(session_id, "assistant", content)
            last_saved_id = saved["id"]
            think = think_by_id.get(message.id, "")
            if think:
                db.add_message_part(saved["id"], "think", think, order=0)
        index += 1
    return last_saved_id

def _extract_final_content(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return _content_text(message.content)
    return ""


def _extract_token_usage(
    messages: list[Any],
    input_messages: list[Any],
    final_content: str,
) -> dict[str, Any] | None:
    """Token consumption of this turn: real API usage when the provider reports
    it (usage_metadata), otherwise a local estimate."""
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        meta = getattr(message, "usage_metadata", None)
        if isinstance(meta, dict):
            inp = int(meta.get("input_tokens") or 0)
            out = int(meta.get("output_tokens") or 0)
            total = int(meta.get("total_tokens") or 0) or (inp + out)
            if total > 0:
                return {
                    "input": inp,
                    "output": out,
                    "total": total,
                    "source": "real",
                }
        break

    from .compact import estimate_tokens

    input_text = "".join(
        _content_text(message.content) for message in input_messages
    )
    inp = estimate_tokens(input_text)
    out = estimate_tokens(final_content)
    if inp + out > 0:
        return {
            "input": inp,
            "output": out,
            "total": inp + out,
            "source": "estimated",
        }
    return None

def _sync_todos_from_state(
    session_id: str, final_state: dict[str, Any]
) -> None:
    todos = final_state.get("todos")
    if todos is None:
        return
    titles = [
        str(todo.get("content") or "").strip()
        for todo in todos
        if str(todo.get("content") or "").strip()
    ]
    db.replace_todos(session_id, titles)

def _frontend_tool_result(output: dict[str, Any]) -> dict[str, Any]:
    result = dict(output)
    for key in ("content", "stdout", "stderr"):
        value = result.get(key)
        if isinstance(value, str) and len(value) > 4000:
            result[key] = value[:4000] + f"\n...[截断，共 {len(value)} 字符]"
    data = result.get("data")
    if isinstance(data, dict):
        data_copy = dict(data)
        for key in ("content", "stdout", "stderr", "text"):
            value = data_copy.get(key)
            if isinstance(value, str) and len(value) > 4000:
                data_copy[key] = (
                    value[:4000] + f"\n...[截断，共 {len(value)} 字符]"
                )
        results = data_copy.get("results")
        if isinstance(results, list) and len(results) > 12:
            data_copy["results"] = results[:12] + [
                {"truncated": True, "count": len(results) - 12}
            ]
        result["data"] = data_copy
    return result
