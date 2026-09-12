from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "remember",
    "保存用户稳定的偏好/事实/习惯/重要事件到长期记忆；不要记临时指令、闲聊、一次性请求、"
    "密码/证件号等敏感信息。纠正/推翻旧记忆时，先用 recall_memories 查到旧记忆的 id，"
    "通过 supersede_id 传入，系统会让旧记忆过期并留痕。",
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
            "scope": {
                "type": "string",
                "enum": ["user", "project"],
                "description": "user=全局用户记忆（默认），project=当前项目的约定/规范（如代码规范、构建命令）",
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
            "scope": str(arguments.get("scope") or "user"),
        }


@register_tool(
    "forget_memory",
    "当用户说“你记错了/忘掉 X/删掉那条记忆”时调用，删除一条长期记忆。"
    "content 传用户提到的那条记忆的原话或大意（支持模糊匹配）；"
    "若系统返回多个候选，向用户确认后带 memory_id 重新调用。",
    {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要忘记的记忆内容，尽量用用户的原话或大意",
            },
            "memory_id": {
                "type": "string",
                "description": "（可选）要删除的记忆 id；多候选确认后使用",
            },
        },
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
            "memory_id": str(arguments.get("memory_id") or ""),
        }


@register_tool(
    "recall_memories",
    "主动检索长期记忆。当系统注入的“已知用户信息”不足以回答、用户提及过去的偏好/事实、"
    "或纠正记忆前需要查旧记忆 id 时调用。",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索内容，如“编程语言偏好”“用户的食物禁忌”",
            },
            "scope": {
                "type": "string",
                "enum": ["user", "project", "session"],
                "description": "user=全局用户记忆（默认），project=当前项目记忆，session=历史会话结论",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "返回条数，默认 5",
            },
        },
        "required": ["query"],
    },
)
class RecallMemoriesAdapter(ToolAdapter):
    script_name = "memory.py"
    category = "memory"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "recall",
            "query": str(arguments.get("query") or ""),
            "scope": str(arguments.get("scope") or "user"),
            "limit": arguments.get("limit", 5),
        }
