from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "manage_model_providers",
    "查看或修改模型提供商目录（新增/更新/删除提供商及其可选模型列表）。"
    "当用户要求新增模型提供商、调整某提供商的模型列表或 base_url 时调用；"
    "改动写入 divine-model-provider.json，用户重新打开设置或重启后生效。",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "upsert", "remove"],
                "description": "list=查看当前目录，upsert=新增或更新，remove=删除",
            },
            "provider": {
                "type": "object",
                "description": "upsert 时的提供商条目：value(必填英文标识)/label(显示名)/base_url/"
                "default_model/list(模型列表)/prefix(模型名前缀)",
            },
            "value": {
                "type": "string",
                "description": "remove 时要删除的提供商 value",
            },
        },
        "required": ["action"],
    },
)
class ManageModelProvidersAdapter(ToolAdapter):
    script_name = "model_providers.py"
    category = "memory"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": str(arguments.get("action") or "list"),
            "provider": arguments.get("provider") or {},
            "value": str(arguments.get("value") or ""),
        }
