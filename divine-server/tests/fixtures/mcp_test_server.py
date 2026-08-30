"""MCP 测试用 stdio server：提供两个确定性工具，供 manager 集成测试使用。

用法：`python tests/fixtures/mcp_test_server.py`（stdout 走 JSON-RPC 协议，
日志一律不得污染 stdout——FastMCP 默认把日志写到 stderr，满足要求）。
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("test-server")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"hello, {name}!"


if __name__ == "__main__":
    mcp.run()
