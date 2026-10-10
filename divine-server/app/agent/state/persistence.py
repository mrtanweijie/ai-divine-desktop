"""Persist LangGraph messages and tool turns into the SQLite session model."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from ... import db
from ..core import _content_text
from ...llm.think_tags import strip_think_tags

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

def _collect_ui_surfaces(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """本轮 ``render_ui`` 产出的面板最终态（044 §5.3）。

    为什么从 ``tool_calls`` 的 **arguments** 重建，而不是从 tool result 取：
    给模型的 result content 只有规模摘要（省 token，§5.4），完整 IR 不进
    ``ToolMessage``。而 arguments 里就是完整 IR —— 重跑一次 validator
    （纯 CPU、无 IO）即可拿到与当时**一致**的归一化结果，
    无状态、可重启、天然幂等。

    任何异常都吞掉：落库不能因为一块面板出问题而整轮失败。
    """
    # 延迟导入：persistence 属于 agent 内核，不希望在模块加载期就拉进
    # tools 包的注册副作用（与 `_extract_token_usage` 里延迟导入 compact 同理）。
    from ...tools.ui.ir import extract_surface
    from ...tools.ui.validator import validate_ui_surface

    surfaces: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if name != "render_ui":
            continue
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
        if not isinstance(args, dict):
            continue
        try:
            validation = validate_ui_surface(extract_surface(args))
        except Exception:  # noqa: BLE001 - 落库不得因面板异常而失败
            continue
        if validation.ok and validation.normalized:
            surfaces.append(validation.normalized)
    return surfaces


def _persist_new_messages(
    session_id: str,
    input_messages: list[Any],
    messages: list[Any],
    think_by_id: dict[str, str],
) -> str | None:
    """Persist new AI/tool messages; return the id of the final assistant
    reply (or None when there is nothing to persist)."""
    last_input_index = -1
    #: 本轮 render_ui 的面板最终态，收敛后挂到最后一条 assistant 消息上
    #: （044 §5.3：面板是"结论的延伸"，必须挂正文消息，而不是承载
    #: tool_calls 的那条空消息 —— 前端会跳过后者）。
    pending_ui_surfaces: list[dict[str, Any]] = []
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
                # 只在"工具全部执行完"时收集面板：没跑完的那轮不算产出（044 §5.3）。
                pending_ui_surfaces.extend(_collect_ui_surfaces(message.tool_calls))
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
    # A2UI 面板最终态（044 §5.3）：挂到最后一条 assistant 正文消息上。
    # 只存最终态、丢弃中间 updateComponents 帧；前端按 type 过滤，order 只作稳定排序。
    # 没有正文消息时（只调工具没输出文字）宁可不落，也不新建空消息污染历史。
    if last_saved_id and pending_ui_surfaces:
        for offset, surface in enumerate(pending_ui_surfaces):
            db.add_message_part(
                last_saved_id,
                "ui_surface",
                json.dumps(surface, ensure_ascii=False),
                order=100 + offset,
            )
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
    """把 agent state 的 todos 合并进本地计划，保留已判定状态。

    修复（D1）：旧实现只取 content 后整表重建为 pending，导致 run 结束后
    进度归零、前端与 DB 分叉。state 为空时不动本地——空只说明本 run 未
    使用 todo（计划重建走 TodoSyncMiddleware 的 replace 路径），不能据此
    清空本地计划。
    """
    todos = final_state.get("todos")
    if todos is None:
        return
    state_status = {
        "pending": "pending",
        "in_progress": "running",
        "completed": "done",
        "cancelled": "skipped",
    }
    items: list[dict[str, Any]] = []
    for todo in todos:
        title = str(todo.get("content") or "").strip()
        if not title:
            continue
        status = state_status.get(
            str(todo.get("status") or "").strip(), "pending"
        )
        items.append({"title": title, "status": status})
    if not items:
        return
    db.sync_todos(session_id, items)

_FRONTEND_STRING_LIMIT = 4000

#: ``data`` 里的整块 payload：前端渲染器需要完整内容，截断会静默丢数据。
#: ``graphIR`` 的 nodes/edges 一旦超过 50 项就会被砍半，图画出来直接缺节点；
#: ``uiSurface``（A2UI 面板）同理——components 超过 50 项会被砍掉后半截，
#: 表现是「复杂面板少了几个组件」而**不报错**，极难排查。
#: 规模已在工具侧强校验（组件数/深度/行数/字节上限），因此这里原样透传。
#: 见 docs/design/020-x6-multi-scenario-20260908.md §3、
#: docs/design/028-a2ui-integration-20261009.md §5.3。
_FRONTEND_OPAQUE_KEYS = frozenset({"graphIR", "uiSurface"})

def _frontend_truncate(value: Any) -> Any:
    """Recursively cap long strings/lists in tool results sent to the UI."""
    if isinstance(value, str):
        if len(value) > _FRONTEND_STRING_LIMIT:
            return value[:_FRONTEND_STRING_LIMIT] + (
                f"\n...[截断，共 {len(value)} 字符]"
            )
        return value
    if isinstance(value, dict):
        return {k: _frontend_truncate(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > 50:
            omitted = len(value) - 50
            return _frontend_truncate(value[:50]) + [
                {"truncated": True, "count": omitted}
            ]
        return [_frontend_truncate(item) for item in value]
    return value

def _frontend_tool_result(output: dict[str, Any]) -> dict[str, Any]:
    result = dict(output)
    for key in ("content", "stdout", "stderr"):
        value = result.get(key)
        if isinstance(value, str) and len(value) > 4000:
            result[key] = value[:4000] + f"\n...[截断，共 {len(value)} 字符]"
    data = result.get("data")
    if isinstance(data, dict):
        data_copy = {}
        for key, value in data.items():
            # 全量 payload（如 graphIR）原样透传；其余字段照旧递归截断。
            data_copy[key] = value if key in _FRONTEND_OPAQUE_KEYS else _frontend_truncate(value)
        results = data_copy.get("results")
        if isinstance(results, list) and len(results) > 12:
            data_copy["results"] = results[:12] + [
                {"truncated": True, "count": len(results) - 12}
            ]
        result["data"] = data_copy
    return result
