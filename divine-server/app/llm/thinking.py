"""Thinking-mode helpers shared by LLM providers (DeepSeek thinking mode).

Aligns with https://api-docs.deepseek.com/zh-cn/guides/thinking_mode:
- The thinking toggle is sent via ``{"thinking": {"type": "enabled|disabled"}}``.
- The user-facing effort vocabulary is low/medium/high/xhigh/max and maps to
  the actual model effort low/high/max (medium/xhigh both map to high).
"""

from __future__ import annotations

from typing import Any

# User-facing effort values -> actual model effort (DeepSeek docs mapping).
_EFFORT_MAP = {
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
    "max": "max",
}

DEFAULT_REASONING_EFFORT = "high"


def normalize_reasoning_effort(value: Any) -> str:
    """Map any documented effort value to the effective model effort.

    Unknown or missing values fall back to the documented default ("high").
    """
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _EFFORT_MAP:
            return _EFFORT_MAP[key]
    return DEFAULT_REASONING_EFFORT


def thinking_extra_body(think: bool) -> dict[str, Any]:
    """OpenAI-format thinking toggle, sent inside ``extra_body``."""
    return {"thinking": {"type": "enabled" if think else "disabled"}}
