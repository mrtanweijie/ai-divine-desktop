"""Provider selection shared by agent runs."""

from __future__ import annotations

from ..config import settings_store
from ..llm import ChatDeepSeekProvider, MockChatModel

def _build_llm() -> Any:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    if provider == "mock":
        return MockChatModel()
    if provider == "langchain":
        return ChatDeepSeekProvider().llm
    if provider == "auto" and not settings.get("api_key"):
        return MockChatModel()
    return ChatDeepSeekProvider().llm
