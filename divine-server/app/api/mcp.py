"""MCP 服务器管理与状态接口（供前端设置页使用）。"""

from __future__ import annotations

from fastapi import APIRouter

from ..mcp.manager import mcp_manager

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers")
async def list_mcp_servers() -> dict:
    """所有已配置 server 的实时状态（含连接尝试与工具清单）。"""
    return {"servers": await mcp_manager.status_all()}


@router.post("/servers/{server_id}/test")
async def test_mcp_server(server_id: str) -> dict:
    """单个 server 的连接测试（设置页"测试连接"按钮）。"""
    return await mcp_manager.status_one(server_id, connect_timeout=10.0)
