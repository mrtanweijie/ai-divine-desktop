from __future__ import annotations

from pydantic import BaseModel, Field


class StreamChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    think: bool = False


class SessionCreate(BaseModel):
    title: str | None = None


class SessionUpdate(BaseModel):
    title: str


class SettingsUpdate(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    workspace_dir: str | None = None
    think_default: bool | None = None
    context_limit: int | None = Field(default=None, ge=1, le=200)
