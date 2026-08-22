"""Runtime context shared by prompt building, tool execution, and streaming."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path


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
