"""Context compaction: token estimation, usage breakdown, and summarization.

Long conversations are collapsed into a running summary persisted in
``session_summaries`` so the model only sees the summary plus the newest
messages. All estimation is local (no LLM calls) so the usage ring in the
UI is free to refresh on every turn.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import db
from ..config import settings_store
from .llm import _build_llm

logger = logging.getLogger("divine.agent.compact")

# Rough local token estimation: CJK ~1 token/char, other text ~4 chars/token.
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_NON_CJK_RE = re.compile(r"[^\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\s]")

# Default context windows per model; extend as needed.
_DEFAULT_CONTEXT_WINDOW = 1_000_000
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-flash-vision-exp": 1_000_000,
    "deepseek-v3": 128_000,
    "deepseek-reasoner": 128_000,
}

# Summary prompt template; {locale} is replaced with a language hint.
_SUMMARY_SYSTEM = (
    "你是对话摘要助手。把用户与 AI 助手的对话压缩为要点摘要。"
    "必须保留：\n"
    "- 用户透露的偏好、身份、个人信息\n"
    "- 已做出的决定和选择\n"
    "- 正在进行的任务及其进度\n"
    "- 关键事实、数字、约束条件\n"
    "- 用户明确要求记住的内容\n"
    "忽略：寒暄、临时指令、工具执行细节、重复内容。\n"
    "如果提供了已有摘要，请与新内容合并、去重并保持连贯。\n"
    "输出 {lang} 摘要，不超过 {budget} 个 token，不要客套话和列表编号。"
)

# Messages above this rowid delta are eligible for compaction when enough
# complete turns have accumulated beyond the current summary cutoff.
_COMPACT_MIN_NEW_ROWS = 12
_COMPACT_MIN_NEW_TURNS = 4


def estimate_tokens(text: str) -> int:
    """Local token estimate: CJK chars ≈ 1 token, other chars ≈ 0.25 token."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(_NON_CJK_RE.findall(text))
    return cjk + round(other / 4)


def context_window(model: str | None = None) -> int:
    entry = _resolve_model_entry()
    name = model or str(entry.get("model") or "")
    return _MODEL_CONTEXT_WINDOWS.get(name, _DEFAULT_CONTEXT_WINDOW)


def _resolve_model_entry() -> dict[str, Any]:
    settings = settings_store.load()
    models = settings.get("models") or []
    for item in models:
        if isinstance(item, dict) and item.get("active"):
            return item
    if models and isinstance(models[0], dict):
        return models[0]
    return {
        "model": settings.get("model") or "deepseek-v4-flash",
        "api_key": settings.get("api_key", ""),
    }


def _system_prompt_preview() -> str:
    """Best-effort preview of the dynamic system prompt for token estimation.

    Mirrors prompts.py::_build_dynamic_prompt parts; exact tokens vary per
    request, which is fine for a usage ring.
    """
    from .constants import SYSTEM_PROMPT
    from ..localization import language_instruction

    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    model_name = settings.get("model") or "deepseek-v4-flash"
    if provider == "mock" or (
        provider == "auto" and not settings.get("api_key")
    ):
        model_line = "当前模型：本地演示模式（Mock）"
    else:
        model_line = f"当前模型：{model_name}"
    locale = settings.get("locale") or "zh-CN"
    parts = [
        SYSTEM_PROMPT.replace("create_plan", "write_todos"),
        language_instruction(locale),
        "当前会话所属项目工作目录：{workspace}\n请以该目录作为方案设计和文件操作的工作区。",
        model_line,
    ]
    return "\n\n".join(parts)


def _tools_preview() -> str:
    """Serialized tool schemas used by the agent, for token estimation."""
    from ..tools.registry import registry

    try:
        return json.dumps(
            registry.openai_schema(), ensure_ascii=False, default=str
        )
    except Exception:  # noqa: BLE001
        return ""


def build_context_breakdown(
    session_id: str, context_limit: int | None = None
) -> dict[str, Any]:
    """Compute per-section token usage for the current session.

    Returns breakdown + totals without triggering any LLM call.
    """
    settings = settings_store.load()
    limit = int(context_limit or settings.get("context_limit") or 20)
    window = context_window()

    system_tokens = estimate_tokens(_system_prompt_preview())
    tools_tokens = estimate_tokens(_tools_preview())
    history = db.history_for_model(session_id, limit=limit)
    messages_tokens = 0
    for message in history:
        content = message.get("content") or ""
        messages_tokens += estimate_tokens(str(content))
        reasoning = message.get("reasoning_content") or ""
        if reasoning:
            messages_tokens += estimate_tokens(str(reasoning))
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            messages_tokens += estimate_tokens(json.dumps(tool_calls))
    total = system_tokens + tools_tokens + messages_tokens
    summary = db.get_summary(session_id)
    compactable = _should_compact(session_id, limit, summary)
    return {
        "usedPercent": (
            round(total * 100 / window) if window > 0 else 0
        ),
        "estimatedTokens": total,
        "contextWindow": window,
        "compactable": bool(compactable),
        "hasSummary": summary is not None and bool(summary.get("summary")),
        "breakdown": {
            "systemPrompt": system_tokens,
            "tools": tools_tokens,
            "messages": messages_tokens,
        },
    }


def _should_compact(
    session_id: str, context_limit: int, summary: dict[str, Any] | None
) -> bool:
    """True when enough new messages accumulated beyond the summary cutoff."""
    cutoff = int((summary or {}).get("cutoff_rowid") or 0)
    rows = _messages_since(session_id, cutoff)
    if len(rows) < _COMPACT_MIN_NEW_ROWS:
        return False
    # Require a few complete user->assistant turns in the new window.
    turns = sum(1 for row in rows if row["role"] == "user")
    return turns >= _COMPACT_MIN_NEW_TURNS


async def compact_session(
    session_id: str, context_limit: int | None = None
) -> dict[str, Any] | None:
    """Summarize messages beyond the current cutoff and persist the summary.

    Returns the saved summary row, or None when there is nothing to compact.
    """
    settings = settings_store.load()
    limit = int(context_limit or settings.get("context_limit") or 20)
    summary = db.get_summary(session_id)
    if not _should_compact(session_id, limit, summary):
        return None

    cutoff = int((summary or {}).get("cutoff_rowid") or 0)
    session = db.get_session(session_id)
    locale = str((session or {}).get("locale") or "zh-CN")

    # Collect messages after the cutoff, plus the tail of the summary window
    # (last few rows before cutoff) so the LLM has context continuity.
    rows = _messages_since(session_id, cutoff)
    if not rows:
        return None
    text = _rows_to_text(rows)
    previous = str((summary or {}).get("summary") or "")

    budget = int(settings.get("summary_token_budget") or 400)
    new_summary = await _summarize(previous, text, budget, locale)
    if not new_summary:
        return None

    newest_rowid = rows[-1]["rowid"]
    saved = db.save_summary(
        session_id,
        new_summary,
        cutoff_rowid=newest_rowid,
        saved_tokens=estimate_tokens(text) - estimate_tokens(new_summary),
    )
    logger.info(
        "session compacted id=%s cutoff=%d tokens=%d",
        session_id,
        newest_rowid,
        saved.get("saved_tokens", 0),
    )
    return saved


def _rows_to_text(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        role = row["role"]
        if role == "tool":
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _messages_since(session_id: str, cutoff_rowid: int) -> list[dict[str, Any]]:
    from contextlib import closing

    from ..db.connection import _connect

    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT rowid, * FROM messages WHERE session_id = ? AND rowid > ? "
            "ORDER BY rowid ASC",
            (session_id, int(cutoff_rowid)),
        ).fetchall()
    return [dict(row) for row in rows]


async def _summarize(
    previous: str, text: str, budget: int, locale: str
) -> str:
    """Run one summarization pass over the given text (best-effort)."""
    lang = {
        "zh-CN": "简体中文",
        "zh-TW": "繁體中文",
        "en": "English",
    }.get(str(locale or ""), "简体中文")
    system = _SUMMARY_SYSTEM.format(lang=lang, budget=budget)
    prompt_parts: list[str] = []
    if previous:
        prompt_parts.append(f"已有摘要：\n{previous}\n")
    prompt_parts.append(f"新增对话：\n{text}\n")
    prompt_parts.append("请输出合并后的摘要。")
    prompt = "\n".join(prompt_parts)

    llm = _build_llm()
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        parts: list[str] = []
        async for chunk in llm.astream(
            [SystemMessage(content=system), HumanMessage(content=prompt)]
        ):
            content = chunk.content
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                )
            text_part = str(content or "").strip()
            if text_part:
                parts.append(text_part)
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary generation failed: %s", exc)
        return ""
    result = "".join(parts).strip()
    if not result:
        return ""
    if estimate_tokens(result) > budget * 2:
        # Over budget: hard-cut at a sentence boundary, keep the head.
        result = result[: budget * 4]
    return result
