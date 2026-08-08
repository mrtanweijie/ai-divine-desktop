from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "create_plan",
    "为复杂任务创建待办计划；执行任务前先调用本工具列出待办事项，后续按待办顺序逐项执行",
    {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "待办事项列表，按执行顺序排列",
            }
        },
        "required": ["items"],
    },
)
class CreatePlanAdapter(ToolAdapter):
    script_name = "plan.py"
    category = "plan"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"items": list(arguments.get("items") or [])}
