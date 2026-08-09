from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "schedule_task",
    "创建或管理定时提醒/定时任务；用户表达“每隔X提醒我”“每天早上X点提醒”“8月10日10点提醒我”等需求时调用；"
    "创建成功后 Agent 会询问用户是否同时写入日程，不要未经询问直接调用 write_calendar",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "update", "pause", "resume", "delete"],
                "description": "操作类型：create 创建，list 查看，update 修改，pause 暂停，resume 恢复，delete 删除",
            },
            "title": {
                "type": "string",
                "description": "提醒/任务标题，例如“买机票”“喝水”",
            },
            "description": {
                "type": "string",
                "description": "提醒详情或任务描述",
            },
            "task_id": {
                "type": "string",
                "description": "update/pause/resume/delete 时必填的任务 id",
            },
            "frequency": {
                "type": "string",
                "enum": ["once", "interval", "daily", "weekly", "monthly"],
                "description": "once 一次性；interval 按分钟间隔；daily 每天；weekly 每周；monthly 每月",
            },
            "interval_minutes": {
                "type": "integer",
                "description": "interval 模式下的间隔分钟数",
            },
            "run_at": {
                "type": "string",
                "description": "一次性任务的 ISO 8601 时间，例如 2026-08-10T10:00:00+08:00",
            },
            "run_hour": {
                "type": "integer",
                "description": "daily/weekly/monthly 模式的小时（0-23）",
            },
            "run_minute": {
                "type": "integer",
                "description": "daily/weekly/monthly 模式的分钟（0-59）",
            },
            "days_of_week": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "weekly 模式运行的星期，0=周一 ... 6=周日",
            },
            "day_of_month": {
                "type": "integer",
                "description": "monthly 模式运行的日期（1-31）",
            },
        },
        "required": ["action"],
    },
)
class ScheduleTaskAdapter(ToolAdapter):
    script_name = "schedule_task.py"
    category = "schedule"
    timeout = 15

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "action": str(arguments.get("action") or "list"),
        }
        for key in (
            "title",
            "description",
            "task_id",
            "frequency",
            "run_at",
            "days_of_week",
        ):
            if arguments.get(key) is not None:
                params[key] = arguments[key]
        for key in (
            "interval_minutes",
            "run_hour",
            "run_minute",
            "day_of_month",
        ):
            if arguments.get(key) is not None:
                try:
                    params[key] = int(arguments[key])
                except (TypeError, ValueError):
                    params[key] = arguments[key]
        return params
