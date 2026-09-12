"""会话收尾的隐式记忆抽取（设计 022 §5.5，P3）。

触发点：``compact_session``——本架构中会话没有显式"结束事件"，压缩在
累积了足够多完整对话轮次后触发，是最稳健的"收尾"挂点（设计 v2 实施注记）。

链路：本地小模型对增量对话抽取候选记忆（带 confidence）→
- confidence ≥ 0.85：直接入库（active，走常规冲突消解）；
- 其余：入库为 pending，进入待确认队列（复用一期消费入口）。

全程 best-effort：本地模型不可用 / 输出不可解析 / 落库失败都静默跳过，
绝不影响压缩主流程，也绝不写入低质记忆。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("divine.agent.memory_extract")

# 高置信阈值：达到即免确认入库，其余进待确认队列。
_AUTO_STORE_CONFIDENCE = 0.85
# 单次抽取的候选上限（防本地模型失控刷库）。
_MAX_CANDIDATES = 5

_ALLOWED_CATEGORIES = ("preference", "fact", "event")

_EXTRACT_SYSTEM = (
    "你是记忆抽取助手。从对话中抽取值得长期记住的用户信息：稳定的偏好、"
    "身份/事实、重要事件。不要抽取：临时指令、闲聊、工具细节、密码/证件号/"
    "银行卡号等敏感信息、对话里已经过时的说法。\n"
    "没有值得记的就返回空数组。\n"
    '只输出 JSON 数组，每项形如 {"content": "一句话", "category": '
    '"preference|fact|event", "importance": 0到1, "confidence": 0到1}。'
)


def parse_candidates(raw: str) -> list[dict[str, Any]]:
    """解析本地模型输出为候选列表；解析失败/非法项一律丢弃。"""
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    parsed: list[dict[str, Any]] = []
    for item in items[:_MAX_CANDIDATES * 2]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        category = str(item.get("category") or "").strip()
        if not content or len(content) > 200:
            continue
        if category not in _ALLOWED_CATEGORIES:
            continue

        def _clamp(value: Any, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return default

        parsed.append(
            {
                "content": content,
                "category": category,
                "importance": _clamp(item.get("importance"), 0.5),
                "confidence": _clamp(item.get("confidence"), 0.5),
            }
        )
        if len(parsed) >= _MAX_CANDIDATES:
            break
    return parsed


def store_candidates(
    session_id: str, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """候选落库：高置信直接 active，其余 pending；重复内容跳过。

    返回实际写入的记忆列表。
    """
    from .. import db

    stored: list[dict[str, Any]] = []
    known = {
        str(m.get("content") or "").strip()
        for status in ("active", "pending")
        for m in db.list_memories(status=status, limit=500)
    }
    for candidate in candidates:
        content = str(candidate.get("content") or "").strip()
        if not content or content in known:
            continue
        confidence = float(candidate.get("confidence") or 0.0)
        try:
            memory = db.save_memory(
                content,
                category=str(candidate["category"]),
                importance=float(candidate.get("importance") or 0.5),
                confidence=confidence,
                source_session_id=session_id,
                status=(
                    "active" if confidence >= _AUTO_STORE_CONFIDENCE else "pending"
                ),
            )
        except (ValueError, KeyError):
            continue
        known.add(content)
        stored.append(memory)
    return stored


async def extract_and_store(
    session_id: str, dialog_text: str
) -> list[dict[str, Any]]:
    """用本地小模型抽取候选记忆并落库；本地模型不可用返回空。"""
    if not str(dialog_text or "").strip():
        return []
    try:
        from .core.local_llm import get_manager

        manager = get_manager()
    except Exception:  # noqa: BLE001
        return []
    if not manager.is_ready():
        return []

    import asyncio

    import requests

    def _call() -> str | None:
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": f"对话内容：\n{dialog_text}"},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }
        try:
            r = requests.post(
                f"http://127.0.0.1:{manager.port}/v1/chat/completions",
                json=payload,
                timeout=60.0,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001 — 抽取绝不打断主流程
            return None

    raw = await asyncio.to_thread(_call)
    if not raw:
        return []
    candidates = parse_candidates(raw)
    if not candidates:
        return []
    stored = store_candidates(session_id, candidates)
    if stored:
        logger.info(
            "implicit memories stored session=%s count=%d",
            session_id,
            len(stored),
        )
    return stored
