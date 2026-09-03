"""用户插话注入中间件：执行中把用户主动补充的信息送进下一次模型调用。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from ..core import AgentRunContext
from ..core.injection import drain_injections


class UserInjectionMiddleware(AgentMiddleware):
    """在每次模型调用前 drain 该 session 的插话队列并追加进 state。

    生效点为"下一个模型调用节点"：正在生成的 token 不受影响
    （流式生成的物理边界），已排队的插话在当前工具批次结束后、
    下一次模型调用前进入上下文。实现异步钩子 abefore_model
    （与 TodoSyncMiddleware 实现 awrap_tool_call 同风格）。
    """

    def __init__(self, ctx: AgentRunContext) -> None:
        super().__init__()
        self.ctx = ctx

    async def abefore_model(
        self, state: Any, runtime: Any
    ) -> dict[str, Any] | None:
        items = drain_injections(self.ctx.session_id)
        if not items:
            return None
        return {"messages": [HumanMessage(content=item) for item in items]}
