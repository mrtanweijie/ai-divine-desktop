"""Runtime context shared by prompt building, tool execution, and streaming."""

from __future__ import annotations

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
