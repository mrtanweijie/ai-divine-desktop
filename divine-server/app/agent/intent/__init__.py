"""Intent subpackage: intent classification + local desktop actions."""

from __future__ import annotations

from .intent import (
    ALWAYS_SECTIONS,
    CONDITIONAL_SECTIONS,
    _ABS_PATH_RE,
    _INTENT_ORDER,
    _looks_like_abs_path,
    build_rule_sections,
    classify_intents,
    estimate_rule_sections_tokens,
    intents_from_tool_history,
    is_question_like,
    strip_abs_paths,
)
from .local_actions import execute_local_action

__all__ = [
    "ALWAYS_SECTIONS",
    "CONDITIONAL_SECTIONS",
    "build_rule_sections",
    "classify_intents",
    "estimate_rule_sections_tokens",
    "intents_from_tool_history",
    "is_question_like",
    "execute_local_action",
]
