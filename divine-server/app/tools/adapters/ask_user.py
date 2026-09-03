"""ask_user: pause the agent to collect a structured answer from the user.

The adapter itself is a marker only — the real behavior lives in
``app/agent/tools/execution.py`` (``_handle_ask_user``), which intercepts the
call before generic dispatch, pauses via LangGraph ``interrupt()``, and turns
the user's answer into the tool result the model sees on resume.
"""

from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool

ASK_USER_DESCRIPTION = (
    "当需要澄清模糊需求、让用户在多个合理方案间选择、或获取只有用户"
    "才知道的关键信息（预算、偏好、账号、路径等）时，调用此工具向用户"
    "提问并等待回答。\n"
    "适用：需求有歧义且直接影响执行结果；存在多个都合理的方案需要用户"
    "拍板；缺失只有用户能提供的信息。\n"
    "不适用：简单的 yes/no 执行确认（已有独立确认机制）；你能从上下文"
    "或记忆推断的信息；对结果没有影响的细节。\n"
    "约束：每次只问一个最关键的问题；能给出候选选项（options + "
    "input_type=single_choice）就不要用开放文本；question 里说明为什么问"
    "（如：为了确定文档风格，需要确认标题字号）。"
)


@register_tool(
    "ask_user",
    ASK_USER_DESCRIPTION,
    {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "要问的问题。说明为什么问，方便用户快速回答，如"
                    "“为了确定文档排版风格，需要确认标题字号，请选择或补充”。"
                ),
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "候选选项（最多 8 个，每个不超过 40 字）。提供时前端"
                    "渲染为可点选项；不提供则用户自由输入。"
                ),
            },
            "input_type": {
                "type": "string",
                "enum": ["text", "single_choice"],
                "description": (
                    "single_choice=单选（需配合 options，用户点击即提交）；"
                    "text=自由文本。默认 text。"
                ),
            },
        },
        "required": ["question"],
    },
)
class AskUserAdapter(ToolAdapter):
    category = "interaction"

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments
