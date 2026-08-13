from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def error_event(
    code: str,
    message: str,
    message_key: str | None = None,
    message_params: dict[str, Any] | None = None,
) -> str:
    data: dict[str, Any] = {"code": code, "message": message}
    if message_key:
        data["messageKey"] = message_key
        data["messageParams"] = message_params or {}
    return sse_event("error", data)
