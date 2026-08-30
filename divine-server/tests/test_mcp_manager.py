"""MCP 客户端管理器集成测试：用真实 stdio fixture server 走完整协议。

覆盖：工具发现与注册名、工具调用、结果展平、禁用 server 跳过、
启动失败容错、配置变更重连、env 密钥合并。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SERVER_SCRIPT = str(
    Path(__file__).resolve().parent / "fixtures" / "mcp_test_server.py"
)


def _patch_servers(monkeypatch, servers: list[dict]) -> None:
    from app.config import settings_store

    monkeypatch.setattr(
        settings_store, "load", lambda: {"mcp_servers": servers}, raising=True
    )
    from app.mcp import manager as mcp_manager_module

    monkeypatch.setattr(
        mcp_manager_module,
        "settings_store",
        settings_store,
        raising=True,
    )


@pytest.fixture()
def fresh_manager(monkeypatch):
    from app.mcp.manager import McpManager

    manager = McpManager()
    yield manager
    import asyncio

    asyncio.run(manager.shutdown())


def _server_cfg(server_id: str = "test", **overrides) -> dict:
    config = {
        "id": server_id,
        "name": server_id,
        "transport": "stdio",
        "command": sys.executable,
        "args": [SERVER_SCRIPT],
        "env": {},
        "enabled": True,
        "trusted": False,
    }
    config.update(overrides)
    return config


def test_discovery_and_call(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(monkeypatch, [_server_cfg()])
    import asyncio

    tools = asyncio.run(fresh_manager.refresh_tool_index(force=True))
    keys = {tool.key for tool in tools}
    assert "mcp_test_add" in keys
    assert "mcp_test_greet" in keys
    add_info = fresh_manager.resolve("mcp_test_add")
    assert add_info is not None
    assert add_info.server_id == "test"
    assert add_info.trusted is False

    result = asyncio.run(
        fresh_manager.call("mcp_test_add", {"a": 2, "b": 3})
    )
    assert result.strip() == "5"

    greeting = asyncio.run(
        fresh_manager.call("mcp_test_greet", {"name": "divine"})
    )
    assert "divine" in greeting


def test_call_reuses_connection_without_respawn(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(monkeypatch, [_server_cfg()])

    async def flow() -> tuple[bool, bool, bool]:
        # 断言所需状态必须在事件循环存续期间读取：
        # asyncio.run 返回时会取消仍在等待的 keeper 任务（生产是常驻循环）。
        await fresh_manager.refresh_tool_index(force=True)
        await fresh_manager.call("mcp_test_add", {"a": 1, "b": 1})
        keeper = fresh_manager._keepers.get("test")
        connected = keeper is not None and keeper.state == "connected"
        await fresh_manager.call("mcp_test_add", {"a": 2, "b": 2})
        after = fresh_manager._keepers.get("test")
        return connected, after is keeper, after is not None

    import asyncio

    connected, reused, present = asyncio.run(flow())
    assert connected
    assert reused
    assert present


def test_disabled_server_skipped(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(monkeypatch, [_server_cfg(enabled=False)])
    import asyncio

    tools = asyncio.run(fresh_manager.refresh_tool_index(force=True))
    assert tools == []


def test_broken_server_isolated(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(
        monkeypatch,
        [
            _server_cfg("broken", command=sys.executable, args=["-c", "import sys; sys.exit(1)"]),
            _server_cfg("test"),
        ],
    )
    import asyncio

    tools = asyncio.run(fresh_manager.refresh_tool_index(force=True))
    # 坏 server 不产生工具，也不拖垮好 server
    assert {tool.key for tool in tools} == {"mcp_test_add", "mcp_test_greet"}
    status = asyncio.run(fresh_manager.status_one("broken", connect_timeout=5))
    assert status["status"] == "error"
    good = asyncio.run(fresh_manager.status_one("test", connect_timeout=8))
    assert good["status"] == "connected"


def test_config_change_reconnects(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(monkeypatch, [_server_cfg(env={})])
    import asyncio

    asyncio.run(fresh_manager.refresh_tool_index(force=True))
    old_keeper = fresh_manager._keepers.get("test")
    assert old_keeper is not None
    # 改配置 → 指纹变化 → 下次访问重建连接
    _patch_servers(monkeypatch, [_server_cfg(env={"FOO": "1"})])
    asyncio.run(fresh_manager.refresh_tool_index(force=True))
    new_keeper = fresh_manager._keepers.get("test")
    assert new_keeper is not old_keeper


def test_status_all_reports_disabled(tmp_path, monkeypatch, fresh_manager):
    _patch_servers(monkeypatch, [_server_cfg(enabled=False)])
    import asyncio

    statuses = asyncio.run(fresh_manager.status_all())
    assert len(statuses) == 1
    assert statuses[0]["status"] == "disabled"


def test_merge_mcp_updates_keeps_secrets():
    from app.api.settings import merge_mcp_updates

    stored = [
        {
            "id": "test",
            "name": "test",
            "env": {"GITHUB_TOKEN": "secret-1"},
        }
    ]
    merged = merge_mcp_updates(
        stored,
        [
            {
                "id": "test",
                "name": "renamed",
                "env": {"GITHUB_TOKEN": "", "NEW_KEY": "v2"},
            }
        ],
    )
    assert len(merged) == 1
    # 空值回填已存密钥；新键正常写入
    assert merged[0]["env"]["GITHUB_TOKEN"] == "secret-1"
    assert merged[0]["env"]["NEW_KEY"] == "v2"
    assert merged[0]["name"] == "renamed"
