"""Tests for the tool plugin loading mechanism."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.registry import (
    _LOADED_PLUGINS,
    get_tool,
    load_plugin_module,
    load_plugins_from,
    registry,
)

_PLUGIN_SOURCE = '''
from __future__ import annotations

from typing import Any

from app.tools.base import ToolAdapter, ToolResult
from app.tools.registry import register_tool


@register_tool(
    "test_plugin_tool",
    "测试插件工具",
    {
        "type": "object",
        "properties": {
            "value": {"type": "integer", "description": "输入值"},
        },
    },
)
class TestPluginTool(ToolAdapter):
    category = "plugin"
    timeout = 5

    async def run(self, workspace, arguments, locale=None, progress_callback=None):
        return ToolResult(
            success=True,
            message="ok",
            content=str(arguments.get("value", 0)),
        )
'''

_BROKEN_PLUGIN_SOURCE = "raise RuntimeError('broken plugin')"


@pytest.fixture(autouse=True)
def _cleanup():
    """Remove any plugin tool / loaded-module state left by a test."""
    yield
    registry.unregister("test_plugin_tool")
    _LOADED_PLUGINS.clear()
    import sys

    for name in list(sys.modules):
        if name.startswith("divine_plugin_") or name == "my_tool":
            sys.modules.pop(name, None)


def test_plugin_module_import(tmp_path: Path) -> None:
    """importlib-based plugin module registers its adapter."""
    plugin_file = tmp_path / "my_tool.py"
    plugin_file.write_text(_PLUGIN_SOURCE, encoding="utf-8")
    sys_path = __import__("sys")
    sys_path.path.insert(0, str(tmp_path))
    try:
        added = load_plugin_module("my_tool")
    finally:
        sys_path.path.remove(str(tmp_path))
    assert added == 1
    tool = get_tool("test_plugin_tool")
    assert tool is not None
    assert tool.category == "plugin"


def test_plugin_directory_scan(tmp_path: Path) -> None:
    """load_plugins_from scans *.py files (skipping underscore-prefixed)."""
    (tmp_path / "good.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "_disabled.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "bad.py").write_text(_BROKEN_PLUGIN_SOURCE, encoding="utf-8")

    added = load_plugins_from(tmp_path)
    # 只有 good.py 成功（bad.py 抛错被跳过，_disabled.py 被跳过）
    assert added == 1
    assert get_tool("test_plugin_tool") is not None


def test_plugin_scan_is_idempotent(tmp_path: Path) -> None:
    """Re-scanning the same directory does not double-register."""
    (tmp_path / "good.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    first = load_plugins_from(tmp_path)
    second = load_plugins_from(tmp_path)
    assert first == 1
    assert second == 0
    assert get_tool("test_plugin_tool") is not None


def test_broken_plugin_does_not_kill_scan(tmp_path: Path) -> None:
    """A failing plugin is skipped; the scan completes and other tools load."""
    (tmp_path / "bad.py").write_text(_BROKEN_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "good.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    added = load_plugins_from(tmp_path)
    assert added == 1
    assert get_tool("test_plugin_tool") is not None


def test_unregister_removes_tool(tmp_path: Path) -> None:
    """unregister drops the tool from the registry."""
    (tmp_path / "good.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    load_plugins_from(tmp_path)
    assert get_tool("test_plugin_tool") is not None
    assert registry.unregister("test_plugin_tool") is True
    assert get_tool("test_plugin_tool") is None
    assert registry.unregister("test_plugin_tool") is False
