from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "write_calendar",
    "把用户输入的内容写入日程/日历；可单独使用，也可在定时提醒创建后按用户确认写入；"
    "从用户输入中识别标题、开始时间、结束时间和备注，例如“8月10日10点买机票”",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "delete", "list"],
                "description": "操作类型：create 创建，update 修改，delete 删除，list 查看",
            },
            "title": {
                "type": "string",
                "description": "日程标题，例如“买机票”",
            },
            "start_at": {
                "type": "string",
                "description": "开始时间，ISO 8601 格式，例如 2026-08-10T10:00:00+08:00",
            },
            "end_at": {
                "type": "string",
                "description": "结束时间，ISO 8601 格式；不传则默认开始后 1 小时",
            },
            "notes": {
                "type": "string",
                "description": "日程备注",
            },
            "location": {
                "type": "string",
                "description": "地点",
            },
            "event_id": {
                "type": "string",
                "description": "update/delete 时必填的日程 id",
            },
            "task_id": {
                "type": "string",
                "description": "由定时提醒创建日程时关联的任务 id",
            },
        },
        "required": ["action"],
    },
)
class WriteCalendarAdapter(ToolAdapter):
    script_name = "write_calendar.py"
    category = "calendar"
    timeout = 15

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "action": str(arguments.get("action") or "list"),
        }
        for key in (
            "title",
            "start_at",
            "end_at",
            "notes",
            "location",
            "event_id",
            "task_id",
        ):
            if arguments.get(key) is not None:
                params[key] = arguments[key]
        return params
