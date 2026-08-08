from __future__ import annotations

from typing import Any

from .base import ToolAdapter


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolAdapter] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        adapter_cls: type[ToolAdapter],
    ) -> ToolAdapter:
        adapter = adapter_cls(name=name, description=description, parameters=parameters)
        self._tools[name] = adapter
        return adapter

    def get(self, name: str) -> ToolAdapter | None:
        return self._tools.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    def openai_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]


registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
):
    def decorator(adapter_cls: type[ToolAdapter]) -> type[ToolAdapter]:
        registry.register(
            name, description, parameters or {"type": "object", "properties": {}}, adapter_cls
        )
        return adapter_cls

    return decorator


def get_tool(name: str) -> ToolAdapter | None:
    return registry.get(name)


def list_tools() -> list[dict[str, Any]]:
    return registry.list()
