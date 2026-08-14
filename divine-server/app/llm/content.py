"""Content normalization helpers shared by LLM providers."""

from __future__ import annotations

from typing import Any

def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if value:
                    parts.append(str(value))
        return "".join(parts)
    return str(content) if content else ""
