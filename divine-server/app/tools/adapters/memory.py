from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "remember",
    "保存用户稳定的偏好/事实/习惯/重要事件到长期记忆；不要记临时指令、闲聊、一次性请求、"
    "密码/证件号等敏感信息。纠正/推翻旧记忆时，先查到旧记忆的 id 并通过 supersede_id 传入，"
    "系统会让旧记忆过期并留痕。",
    {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "一句话概括要记住的内容，如“用户偏好 TypeScript，不喜欢 Python”",
            },
            "category": {
                "type": "string",
                "enum": ["preference", "fact", "event"],
                "description": "preference=偏好，fact=事实，event=重要事件",
            },
            "importance": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "重要性 0-1，默认 0.5",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "确信度 0-1，默认 0.8",
            },
            "supersede_id": {
                "type": "string",
                "description": "（可选）被本条记忆取代的旧记忆 id。更新用户改述过的旧偏好/事实时必传",
            },
        },
        "required": ["content", "category"],
    },
)
class RememberAdapter(ToolAdapter):
    script_name = "memory.py"
    category = "memory"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "remember",
            "content": str(arguments.get("content") or ""),
            "category": str(arguments.get("category") or "preference"),
            "importance": arguments.get("importance", 0.5),
            "confidence": arguments.get("confidence", 0.8),
            "supersede_id": str(arguments.get("supersede_id") or ""),
        }


@register_tool(
    "forget_memory",
    "当用户说“你记错了/忘掉 X/删掉那条记忆”时调用，删除一条长期记忆。"
    "content 传用户提到的那条记忆的原话或大意。",
    {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要忘记的记忆内容，尽量用用户的原话",
            }
        },
        "required": ["content"],
    },
)
class ForgetMemoryAdapter(ToolAdapter):
    script_name = "memory.py"
    category = "memory"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "forget",
            "content": str(arguments.get("content") or ""),
        }
