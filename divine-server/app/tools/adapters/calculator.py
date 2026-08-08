from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "calculator",
    "安全计算数学表达式，支持四则运算、比较、逻辑和常用数学函数（sqrt、sin、cos、log、pow 等）",
    {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，例如 (1+2)*3、sqrt(144)、2**10",
            }
        },
        "required": ["expression"],
    },
)
class CalculatorAdapter(ToolAdapter):
    script_name = "calculator.py"
    category = "system"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"expression": str(arguments.get("expression") or "")}
