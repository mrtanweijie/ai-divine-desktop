"""Central tool registry.

Built-in tools are registered via the :func:`register_tool` decorator when
``app.tools.adapters`` is imported (its ``__init__`` statically imports every
adapter module, which triggers the decorator side effect).

Plugins can be loaded at runtime: :func:`load_plugin_module` imports a Python
module and registers any ``@register_tool`` adapters it defines, and
:func:`load_plugins_from` scans a directory for such modules. Plugins are
ordinary Python modules with the same adapter API as built-ins, so they share
the full execution pipeline (approval, terminal policy, timeouts, tool runs).

The registry is a plain dict keyed by tool name; unloading simply removes the
entry (already-built LLM schemas pick it up on the next session).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from .base import ToolAdapter

logger = logging.getLogger("divine.tools.registry")


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

    def unregister(self, name: str) -> bool:
        """Remove a tool by name; returns True if it existed."""
        return self._tools.pop(name, None) is not None

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

    def names(self) -> set[str]:
        return set(self._tools)


registry = ToolRegistry()

# Plugin modules already loaded by synthetic name (avoids double-loading).
_LOADED_PLUGINS: set[str] = set()


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


def load_plugin_module(module_name: str) -> int:
    """Import a plugin module, registering any ``@register_tool`` adapters.

    Returns the number of tools registered by that module (0 if none).
    Import errors propagate to the caller.
    """
    before = len(registry.names())
    importlib.import_module(module_name)
    added = len(registry.names()) - before
    logger.info("plugin %s registered %d tool(s)", module_name, added)
    return added


def load_plugins_from(plugins_dir: Path) -> int:
    """Scan ``plugins_dir`` for ``*.py`` files and load each as a plugin.

    Each file is imported as a top-level module named ``divine_plugin_<stem>``
    so plugins need no package boilerplate. Broken plugins are logged and
    skipped (startup continues). Returns the total number of tools added.
    """
    if not plugins_dir.is_dir():
        return 0
    total = 0
    for entry in sorted(plugins_dir.glob("*.py")):
        if entry.name.startswith("_"):
            continue
        module_name = f"divine_plugin_{entry.stem}"
        if module_name in _LOADED_PLUGINS:
            continue
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry)
            if spec is None or spec.loader is None:
                logger.warning("插件无法加载（无 spec）: %s", entry.name)
                continue
            before = len(registry.names())
            module = importlib.util.module_from_spec(spec)
            _LOADED_PLUGINS.add(module_name)
            spec.loader.exec_module(module)
            added = len(registry.names()) - before
            total += added
            logger.info("插件文件 %s 注册 %d 个工具", entry.name, added)
        except Exception as exc:  # noqa: BLE001 — broken plugin must not kill startup
            logger.exception("加载插件失败 %s: %s", entry.name, exc)
    return total
