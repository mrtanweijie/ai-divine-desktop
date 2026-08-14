"""Agent orchestration package.

The public entry point is :func:`run_agent`, which streams SSE events for a
single chat turn through LangGraph.
"""

from __future__ import annotations

from .orchestrator import run_agent

__all__ = ["run_agent"]
