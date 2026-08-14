"""LangGraph interrupt helpers for user-in-the-loop approvals."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

_ACTIVE_INTERRUPTS: set[tuple[str, str]] = set()

def _ask_interrupt(
    session_id: str,
    marker: str,
    payload: dict[str, Any],
) -> Any:
    key = (session_id, marker)
    if key not in _ACTIVE_INTERRUPTS:
        _ACTIVE_INTERRUPTS.add(key)
    decision = interrupt(payload)
    _ACTIVE_INTERRUPTS.discard(key)
    return decision
