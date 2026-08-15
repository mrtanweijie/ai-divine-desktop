from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# DeepSeek thinking-mode effort vocabulary (see
# https://api-docs.deepseek.com/zh-cn/guides/thinking_mode).
ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


class Attachment(BaseModel):
    name: str
    content: str = ""
    file_path: str | None = None
    size: int | None = None


class StreamChatRequest(BaseModel):
    question: str = Field(default="")
    session_id: str | None = None
    project_id: str | None = None
    approval_mode: str | None = None
    think: bool = False
    reasoning_effort: ReasoningEffort | None = None
    locale: str | None = None
    attachments: list[Attachment] = []


class SessionCreate(BaseModel):
    title: str | None = None
    project_id: str | None = None
    approval_mode: str | None = None
    locale: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    approval_mode: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    path: str | None = None
    icon: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    path: str | None = None
    icon: str | None = None


class SettingsUpdate(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    glm_api_key: str | None = None
    workspace_dir: str | None = None
    username: str | None = None
    think_default: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    context_limit: int | None = Field(default=None, ge=1, le=200)


class ScheduledTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    session_id: str | None = None
    task_type: Literal["reminder", "agent", "monitor"] = "reminder"
    frequency: Literal["once", "interval", "daily", "weekly", "monthly"] = (
        "interval"
    )
    interval_minutes: int | None = Field(default=None, ge=1)
    run_at: str | None = None
    run_hour: int | None = Field(default=None, ge=0, le=23)
    run_minute: int | None = Field(default=None, ge=0, le=59)
    days_of_week: list[int] = []
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    status: Literal["active", "paused", "done"] = "active"


class ScheduledTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    session_id: str | None = None
    task_type: Literal["reminder", "agent", "monitor"] | None = None
    frequency: Literal["once", "interval", "daily", "weekly", "monthly"] | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    run_at: str | None = None
    run_hour: int | None = Field(default=None, ge=0, le=23)
    run_minute: int | None = Field(default=None, ge=0, le=59)
    days_of_week: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    next_run_at: str | None = None
    last_run_at: str | None = None
    status: Literal["active", "paused", "done"] | None = None
    calendar_synced: int | None = None


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_at: str
    end_at: str | None = None
    notes: str = ""
    location: str = ""
    task_id: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_at: str | None = None
    end_at: str | None = None
    notes: str | None = None
    location: str | None = None
    task_id: str | None = None
    system_event_id: str | None = None
    synced: int | None = None
