"""调试收敛中间件：同一错误的指纹计数与硬刹车（design 026 §4）。

为什么不复用 ``plans.py::_spawn_recovery_todo``：后者的去重键是 ``tool_name``，
同一个 ``AssertionError`` 换个工具跑就绕过了去重；而且它只挂一条用户可见的计划项，
不做"停止自动重试"的刹车。两者职责不同，**共存不合并**：
recovery todo 面向用户可见计划，本中间件面向模型的收敛控制。

收敛为什么放中间件而不是 prompt：``_PROJECT_WORKFLOW`` 里的"最多重试 2 次"
是软约束，模型不遵循即失效。中间件能计数、能强制、能留痕。
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..core import AgentRunContext

# 从工具结果里回收诊断层写下的指纹。诊断段由 ``diagnostics.format_failure_block``
# 生成，格式固定为 ``  fingerprint: <12 位十六进制>``。
_FINGERPRINT_RE = re.compile(r"fingerprint:\s*([0-9a-f]{12})")

# 同一个错误出现到这个次数就硬刹车。与 prompt 里"最多重试 2 次"对齐：
# 第 1 次是首次失败，第 2 次说明上一次改法没生效，第 3 次就该交回用户了。
_HALT_AT = 3

_REPEAT_NOTE = (
    "[调试收敛] 该错误第 2 次出现，上一次的修改没有解决它。"
    "不要重复同样的改法：先加日志/断言确认假设，或换个方向定位。"
)

_HALT_NOTE = (
    "[调试收敛] 已连续 3 次未能修复同一错误，停止自动重试。"
    "请向用户如实汇报：错误信息、已尝试的改法、你判断的根因与建议的下一步。"
    "不要谎报成功。"
)


def _extract_fingerprint(result: Any) -> str:
    """从工具结果里取指纹；取不到返回空串（成功路径与无栈帧失败都会走这里）。"""
    if not isinstance(result, ToolMessage):
        return ""
    content = result.content
    if not isinstance(content, str):
        return ""
    match = _FINGERPRINT_RE.search(content)
    return match.group(1) if match else ""


def _append_note(result: Any, note: str) -> bool:
    """把提示追加到 ToolMessage 尾部。只处理字符串 content。

    list[ContentBlock] 形态（多模态）不在此改写——拼接语义不明确，
    且会破坏前端已有的块渲染契约；那种结果自然享受不到刹车，
    但也不会被改坏。
    """
    if not isinstance(result, ToolMessage):
        return False
    if not isinstance(result.content, str):
        return False
    result.content = f"{result.content}\n\n{note}"
    return True


class DebugLoopMiddleware(AgentMiddleware):
    """按错误指纹计数：第 2 次提醒换思路，第 3 次硬刹车要求如实汇报。

    计数键只有指纹、不带工具名，所以同一个 bug 换工具重跑也会累计
    （这正是旧 ``tool_name`` 去重挡不住的绕过路径）。
    """

    def __init__(self, ctx: AgentRunContext) -> None:
        super().__init__()
        self.ctx = ctx

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        result = await handler(request)
        # 已刹车：不再追加提示，避免在模型汇报前反复刷屏。
        if self.ctx.debug_halt:
            return result
        fingerprint = _extract_fingerprint(result)
        if not fingerprint:
            return result
        count = self.ctx.debug_state.get(fingerprint, 0) + 1
        self.ctx.debug_state[fingerprint] = count
        if count >= _HALT_AT:
            self.ctx.debug_halt = True
            _append_note(result, _HALT_NOTE)
        elif count == 2:
            _append_note(result, _REPEAT_NOTE)
        return result
