"""Shared plumbing for command-style tools (lint_check / run_tests).

These tools never spawn processes themselves: they build a concrete command
string and delegate execution to the terminal tool, so the exact same
policy gate (terminal_command_policy) and approval flow apply. The only
added value is structured output parsing.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from ..base import ToolExecutionError, ToolResult
from ..registry import get_tool


def quote_paths(paths: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in paths)


def resolve_cwd(workspace: Path, arguments: dict[str, Any]) -> Path:
    workspace = workspace.resolve()
    cwd_raw = str(arguments.get("cwd") or "").strip()
    if not cwd_raw:
        return workspace
    cwd = Path(cwd_raw)
    if not cwd.is_absolute():
        cwd = workspace / cwd
    cwd = cwd.resolve()
    try:
        cwd.relative_to(workspace)
    except ValueError as exc:
        raise ToolExecutionError(f"cwd 必须位于工作区内: {cwd}") from exc
    if not cwd.is_dir():
        raise ToolExecutionError(f"目录不存在: {cwd}")
    return cwd


def existing_paths(cwd: Path, raw_paths: list[str]) -> list[str]:
    """Filter requested paths down to those that exist under cwd."""
    result: list[str] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        try:
            resolved = path.resolve()
            resolved.relative_to(cwd)
        except (ValueError, OSError):
            continue
        if resolved.exists():
            result.append(str(resolved.relative_to(cwd)))
    return result


def clamp_timeout(arguments: dict[str, Any], default: int) -> int:
    try:
        requested = int(arguments.get("timeout") or 0)
    except (TypeError, ValueError):
        requested = 0
    return min(max(requested or default, 60), 600)


async def run_via_terminal(
    workspace: Path,
    arguments: dict[str, Any],
    command: str,
    timeout: int,
) -> ToolResult:
    """Execute `command` through the terminal adapter (same policy gate)."""
    terminal = get_tool("terminal")
    if terminal is None:
        raise ToolExecutionError("terminal 工具不可用")
    merged = {
        **arguments,
        "command": command,
        "background": False,
        "cwd": arguments.get("cwd") or "",
        "timeout": timeout,
    }
    return await terminal.run(workspace, merged)


def extract_command_output(result: ToolResult) -> tuple[str, str, int]:
    """Pull (stdout, stderr, exit_code) out of a terminal ToolResult."""
    data = result.data or {}
    stdout = str(data.get("stdout_tail") or data.get("stdout") or "")
    stderr = str(data.get("stderr_tail") or data.get("stderr") or "")
    try:
        exit_code = int(data.get("exit_code") or 0)
    except (TypeError, ValueError):
        exit_code = 0
    return stdout, stderr, exit_code


def build_content_summary(
    title: str,
    parsed_summary: str,
    items: list[dict[str, Any]],
    raw_tail: str,
    max_lines: int = 40,
) -> str:
    lines: list[str] = [f"{title}: {parsed_summary}" if parsed_summary else title]
    for item in items[:max_lines]:
        parts = [
            str(item.get(key))
            for key in ("file", "line", "test", "code", "message")
            if item.get(key) is not None
        ]
        if parts:
            lines.append("  - " + ":".join(parts[:2]) + " " + " ".join(parts[2:]))
    shown = min(len(items), max_lines)
    if len(items) > shown:
        lines.append(f"  ...(其余 {len(items) - shown} 条省略)")
    if not items and raw_tail:
        lines.append(raw_tail[:2000])
    return "\n".join(lines)
