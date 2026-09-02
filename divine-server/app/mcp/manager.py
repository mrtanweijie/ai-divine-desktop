"""MCP (Model Context Protocol) 客户端管理器（v0：stdio 传输）。

配置来自 settings 的 ``mcp_servers`` 列表::

    [{"id": "github", "name": "GitHub", "transport": "stdio",
      "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "..."}, "enabled": true, "trusted": false}]

连接模型（规避 anyio cancel-scope 的任务绑定限制）：
每个 server 一个常驻 keeper 任务，AsyncExitStack 只在 keeper 任务内进入和
退出；list_tools / call_tool / 关闭都以"操作"形式经队列发给 keeper，在同一
任务里执行。这样连接、使用、关闭永远不跨任务，跨任务退出 cancel scope
的经典崩溃不存在，且单 server 的会话操作天然串行。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from ..config import settings_store

logger = logging.getLogger("divine.mcp")

_TOOL_CONNECT_TIMEOUT = 8.0
_TOOL_CALL_TIMEOUT = 180.0
_TOOL_INDEX_TTL = 120.0
_FAILURE_COOLDOWN = 5.0
_MAX_TEXT_CHARS = 40_000

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize(value: str) -> str:
    return _SANITIZE_RE.sub("_", (value or "").strip()).strip("_-")


@dataclass
class McpToolInfo:
    """One MCP tool as injected into the agent's tool list."""

    key: str  # 注册名：mcp_<server>_<tool>
    server_id: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    trusted: bool = False


def load_mcp_servers() -> list[dict]:
    """Read mcp_servers entries from settings (tolerant of bad shapes)."""
    try:
        raw = settings_store.load().get("mcp_servers")
    except Exception:  # noqa: BLE001 — settings 读取失败等同于未配置
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("id")]


def _config_fingerprint(config: dict) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)


class _ServerKeeper:
    """Owns one server connection for its whole lifetime (keeper-task pattern)."""

    def __init__(self, server_id: str, config: dict) -> None:
        self.server_id = server_id
        self.config = config
        self.fingerprint = _config_fingerprint(config)
        self.state = "starting"  # starting | connected | error | stopped
        self.error: str = ""
        self.tools: list[dict] = []
        self._ops: asyncio.Queue = asyncio.Queue()
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(
            self._run(), name=f"mcp-keeper-{self.server_id}"
        )

    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        if self._task is None:
            return
        self.state = "stopped"
        await self._ops.put(None)
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
            self._task.cancel()

    async def list_tools(self, timeout: float = _TOOL_CONNECT_TIMEOUT) -> list[dict]:
        return await self._request("list", timeout=timeout)

    async def call_tool(
        self, name: str, arguments: dict, timeout: float = _TOOL_CALL_TIMEOUT
    ) -> str:
        return await self._request(
            "call", timeout=timeout, name=name, arguments=arguments
        )

    async def _request(self, kind: str, timeout: float, **payload: Any) -> Any:
        if self.state == "error":
            raise RuntimeError(self.error or "MCP server 启动失败")
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        if self.state == "error":
            raise RuntimeError(self.error or "MCP server 启动失败")
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._ops.put((kind, future, payload))
        return await asyncio.wait_for(future, timeout=timeout)

    async def _run(self) -> None:  # noqa: C901 — 单任务持有全部连接生命周期
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        stack = None
        session = None
        try:
            from mcp.client.stdio import get_default_environment

            env = {**get_default_environment(), **(self.config.get("env") or {})}
            params = StdioServerParameters(
                command=str(self.config.get("command") or ""),
                args=[str(a) for a in (self.config.get("args") or [])],
                env=env,
            )
            stack = AsyncExitStack()
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.state = "connected"
            self.error = ""
            self._ready.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.state = "error"
            self.error = f"{type(exc).__name__}: {exc}"
            logger.warning("MCP server %s 连接失败: %s", self.server_id, self.error)
            self._ready.set()
            try:
                if stack is not None:
                    await stack.aclose()
            except Exception:  # noqa: BLE001
                pass
            return

        try:
            while True:
                op = await self._ops.get()
                if op is None:
                    break
                kind, future, payload = op
                if future.done():
                    continue
                try:
                    if kind == "list":
                        result = await session.list_tools()
                        self.tools = [
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                # SDK 1.x 为 inputSchema，2.x 改名 input_schema
                                "inputSchema": (
                                    getattr(tool, "input_schema", None)
                                    or getattr(tool, "inputSchema", None)
                                    or {}
                                ),
                            }
                            for tool in result.tools
                        ]
                        future.set_result(self.tools)
                    elif kind == "call":
                        result = await session.call_tool(
                            payload["name"], payload["arguments"] or {}
                        )
                        future.set_result(_result_text(result))
                    else:
                        future.set_exception(ValueError(f"未知操作 {kind}"))
                except Exception as exc:  # noqa: BLE001
                    if not future.done():
                        future.set_exception(exc)
        except asyncio.CancelledError:
            raise
        finally:
            self.state = "stopped" if self.state != "error" else self.state
            try:
                if stack is not None:
                    await stack.aclose()
            except Exception:  # noqa: BLE001
                pass


def _result_text(result: Any) -> str:
    """Flatten a CallToolResult into model-facing text."""
    if getattr(result, "isError", False):
        text = "\n".join(
            str(getattr(item, "text", "")) for item in (result.content or [])
        ).strip()
        raise RuntimeError(text or "MCP 工具执行失败")
    parts: list[str] = []
    for item in (result.content or []):
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
        else:
            parts.append(f"[非文本内容: {type(item).__name__}]")
    output = "\n".join(parts).strip()
    structured = getattr(result, "structuredContent", None)
    if not output and structured:
        output = json.dumps(structured, ensure_ascii=False, default=str)
    if len(output) > _MAX_TEXT_CHARS:
        output = output[:_MAX_TEXT_CHARS] + f"\n...(已截断，总 {len(output)} 字符)"
    return output


class McpManager:
    """Server/tool registry over settings; lazily connects per server."""

    def __init__(self) -> None:
        self._keepers: dict[str, _ServerKeeper] = {}
        self._index: dict[str, McpToolInfo] = {}
        self._index_ts = 0.0
        self._last_failure: dict[str, float] = {}

    # ---- config ----

    def _enabled_servers(self) -> list[dict]:
        return [s for s in load_mcp_servers() if s.get("enabled", True)]

    def _trusted(self, config: dict) -> bool:
        return bool(config.get("trusted", False))

    # ---- keeper lifecycle ----

    async def _keeper_for(self, server_id: str) -> _ServerKeeper:
        config = next(
            (s for s in self._enabled_servers() if s.get("id") == server_id), None
        )
        if config is None:
            raise RuntimeError(f"MCP server 未配置或已停用: {server_id}")
        fingerprint = _config_fingerprint(config)
        keeper = self._keepers.get(server_id)
        if (
            keeper is not None
            and keeper.fingerprint == fingerprint
            and keeper.alive()
            and keeper.state != "error"
        ):
            return keeper
        if keeper is not None:
            await keeper.stop()
            self._keepers.pop(server_id, None)
        last_fail = self._last_failure.get(server_id, 0.0)
        if time.monotonic() - last_fail < _FAILURE_COOLDOWN:
            raise RuntimeError("MCP server 刚刚启动失败，请稍后重试或检查配置")
        keeper = _ServerKeeper(server_id, config)
        keeper.start()
        self._keepers[server_id] = keeper
        return keeper

    async def _connect(self, server_id: str, timeout: float) -> _ServerKeeper:
        keeper = await self._keeper_for(server_id)
        try:
            await keeper.list_tools(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            self._last_failure[server_id] = time.monotonic()
            await keeper.stop()
            self._keepers.pop(server_id, None)
            if isinstance(exc, asyncio.TimeoutError):
                raise RuntimeError(
                    f"MCP server {server_id} 连接超时（{timeout:.0f}s）"
                ) from exc
            raise
        return keeper

    # ---- public API ----

    async def status_one(self, server_id: str, connect_timeout: float = 8.0) -> dict:
        config = next(
            (s for s in load_mcp_servers() if s.get("id") == server_id), None
        )
        if config is None:
            return {"id": server_id, "status": "error", "error": "配置不存在"}
        if not config.get("enabled", True):
            return {
                "id": server_id,
                "name": config.get("name") or server_id,
                "status": "disabled",
                "tools": [],
            }
        try:
            keeper = await self._connect(server_id, connect_timeout)
            return {
                "id": server_id,
                "name": config.get("name") or server_id,
                "status": "connected",
                "trusted": self._trusted(config),
                "tools": keeper.tools,
            }
        except Exception as exc:  # noqa: BLE001 — 状态接口必须返回而非抛错
            return {
                "id": server_id,
                "name": config.get("name") or server_id,
                "status": "error",
                "error": str(exc)[:300],
                "tools": [],
            }

    async def status_all(self, connect_timeout: float = 8.0) -> list[dict]:
        servers = load_mcp_servers()
        results = await asyncio.gather(
            *(
                self.status_one(str(s.get("id")), connect_timeout)
                for s in servers
            ),
            return_exceptions=True,
        )
        output: list[dict] = []
        for server, result in zip(servers, results):
            if isinstance(result, Exception):
                output.append(
                    {
                        "id": server.get("id"),
                        "name": server.get("name") or server.get("id"),
                        "status": "error",
                        "error": str(result)[:300],
                        "tools": [],
                    }
                )
            else:
                output.append(result)
        return output

    async def refresh_tool_index(self, force: bool = False) -> list[McpToolInfo]:
        """Refresh the tool index (cached); failures leave the old index in place."""
        if (
            not force
            and self._index
            and time.monotonic() - self._index_ts < _TOOL_INDEX_TTL
        ):
            return list(self._index.values())
        index: dict[str, McpToolInfo] = {}
        for server in self._enabled_servers():
            server_id = str(server.get("id"))
            server_name = _sanitize(str(server.get("name") or server_id)) or server_id
            try:
                keeper = await self._connect(server_id, _TOOL_CONNECT_TIMEOUT)
            except Exception as exc:  # noqa: BLE001 — 单 server 失败不拖垮工具注入
                logger.warning("MCP 工具索引跳过 %s: %s", server_id, exc)
                continue
            trusted = self._trusted(server)
            for tool in keeper.tools:
                tool_name = _sanitize(str(tool.get("name") or "")) or "tool"
                key = f"mcp_{server_name}_{tool_name}"
                while key in index:  # 同名工具去重
                    key += "_"
                index[key] = McpToolInfo(
                    key=key,
                    server_id=server_id,
                    server_name=server_name,
                    tool_name=str(tool.get("name") or tool_name),
                    description=str(tool.get("description") or ""),
                    input_schema=tool.get("inputSchema") or {},
                    trusted=trusted,
                )
        if index or force:
            self._index = index
            self._index_ts = time.monotonic()
        return list(self._index.values())

    def snapshot_tools(self) -> list[McpToolInfo]:
        """Sync read of the last-known tool index (for _build_tools)."""
        return list(self._index.values())

    def resolve(self, key: str) -> McpToolInfo | None:
        return self._index.get(key)

    async def call(self, key: str, arguments: dict) -> str:
        info = self._index.get(key)
        if info is None:
            raise RuntimeError(f"MCP 工具不可用: {key}")
        keeper = await self._keeper_for(info.server_id)
        try:
            return await keeper.call_tool(info.tool_name, arguments)
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"MCP 工具 {info.tool_name} 执行超时（{_TOOL_CALL_TIMEOUT:.0f}s）"
            ) from exc
        except Exception:  # noqa: BLE001 — 调用失败后标记，下次重连
            self._last_failure[info.server_id] = time.monotonic()
            raise

    async def shutdown(self) -> None:
        for keeper in list(self._keepers.values()):
            try:
                await keeper.stop()
            except Exception:  # noqa: BLE001
                pass
        self._keepers.clear()


mcp_manager = McpManager()
