"""Runtime context shared by prompt building, tool execution, and streaming.

Also hosts the local token estimator: it is a pure function with no agent
dependencies, and keeping it here (instead of in ``compact``) breaks the
``intent ↔ compact`` lazy import cycle — both sides can import it from the
shared core leaf.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path

# Rough local token estimation: CJK ~1 token/char, other text ~4 chars/token.
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_NON_CJK_RE = re.compile(r"[^\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\s]")


def estimate_tokens(text: str) -> int:
    """Local token estimate: CJK chars ≈ 1 token, other chars ≈ 0.25 token."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(_NON_CJK_RE.findall(text))
    return cjk + round(other / 4)


def canonical_path(path: str | Path, workspace: Path) -> str:
    """Resolve a (possibly workspace-relative) path and normalize it."""
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    return os.path.realpath(p)


@dataclass
class AgentRunContext:
    session_id: str
    workspace: Path
    approval_mode: str
    locale: str = "zh-CN"
    plan_choice_resolved: bool = False
    plan_first_pending: bool = False
    plan_approved: bool = False
    # ask_user 每轮（每次 run）最多一次的硬限计数。
    ask_user_count: int = 0
    # Files the user explicitly attached (selected or pasted): tool access to
    # these exact paths is pre-approved and needs no external-file confirm.
    approved_paths: frozenset[str] = frozenset()
    # Model/thinking settings of the current main run; sub-agents inherit them
    # so a delegated batch keeps the same provider, model, and thinking mode.
    think: bool = False
    effort: str | None = None
    model_id: str | None = None
    # Tool-calling paradigm for this run: "native" (bind_tools) or "react"
    # (ReAct text loop). Resolved before the run starts; defaults to native.
    tool_mode: str = "native"
    # Set when the user stops the main stream; sub-agent batches poll it and
    # abort early instead of finishing work nobody will see.
    cancel_event: asyncio.Event | None = None
    # 本地意图识别结果
    intents: set[str] | None = None
    local_intent_result: dict | None = None
    # 当前 run 的模型调用轮次（TurnCounterMiddleware 维护）。
    # tool 事件携带它，前端据此把工具调用按轮次分组展示。
    turn_index: int = 0
