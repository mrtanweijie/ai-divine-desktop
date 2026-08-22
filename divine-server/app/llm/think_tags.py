"""Incremental ``<think>...</think>`` tag splitter for reasoning models.

Some reasoning models (e.g. MiniMax-M3, GLM-5.x) emit their chain-of-thought
inline in the message content wrapped in ``<think>...</think>`` tags instead
of a dedicated ``reasoning_content`` field. This processor incrementally
splits the text stream so the inner block streams as ``think`` events and
everything else as ``message`` events, mirroring the DeepSeek
``reasoning_content`` path.
"""

from __future__ import annotations

import re

_OPEN = "<think>"
_CLOSE = "</think>"
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think_tags(text: str) -> str:
    """Remove inline ``<think>...</think>`` blocks from a full message string."""
    if not isinstance(text, str) or "<think>" not in text:
        return text
    return _THINK_TAG_RE.sub("", text).strip()


class ThinkTagProcessor:
    """Incremental classifier for inline ``<think>`` blocks.

    Emits ``{"type": "think" | "message", "content": str}`` events. Handles
    partial tags across chunk boundaries by holding back the trailing prefix.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    def push(self, chunk: str) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        self._buffer += chunk
        while True:
            if self._in_think:
                idx = self._buffer.find(_CLOSE)
                if idx == -1:
                    # No close yet: emit everything except the trailing
                    # partial-close prefix, which may still become part of
                    # the tag.
                    keep = max(0, len(self._buffer) - (len(_CLOSE) - 1))
                    if keep:
                        events.append(
                            {"type": "think", "content": self._buffer[:keep]}
                        )
                        self._buffer = self._buffer[keep:]
                    break
                content = self._buffer[:idx]
                if content:
                    events.append({"type": "think", "content": content})
                self._buffer = self._buffer[idx + len(_CLOSE):]
                self._in_think = False
            else:
                idx = self._buffer.find(_OPEN)
                if idx == -1:
                    # No open yet: emit everything except the trailing
                    # partial-open prefix.
                    keep = max(0, len(self._buffer) - (len(_OPEN) - 1))
                    if keep:
                        events.append(
                            {"type": "message", "content": self._buffer[:keep]}
                        )
                        self._buffer = self._buffer[keep:]
                    break
                content = self._buffer[:idx]
                if content:
                    events.append({"type": "message", "content": content})
                self._buffer = self._buffer[idx + len(_OPEN):]
                self._in_think = True
        return events

    def flush(self) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        if self._buffer:
            events.append(
                {
                    "type": "think" if self._in_think else "message",
                    "content": self._buffer,
                }
            )
            self._buffer = ""
        return events
