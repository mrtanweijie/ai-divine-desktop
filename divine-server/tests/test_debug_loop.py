"""调试收敛中间件测试（design 026 P2）。

覆盖：指纹计数 / 二次注入提示 / 三次硬刹车 / 跨工具共享计数 /
刹车后不再注入 / 成功路径零影响 / 异常结果形态不炸 / 中间件链位置。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from app.agent.core.context import AgentRunContext
from app.agent.middleware.debug_loop import (
    _HALT_NOTE,
    _REPEAT_NOTE,
    DebugLoopMiddleware,
)

_FP = "a3f9c21b7e04"


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        session_id="debug-ctx",
        workspace=Path("/tmp"),
        approval_mode="full",
    )


def _content(fingerprint: str = _FP) -> str:
    """模拟 execution.py 追加 [诊断] 段之后的工具结果。"""
    return (
        "Traceback (most recent call last):\n"
        "KeyError: 'x'\n"
        "\n"
        "[诊断] 1 个失败，定位如下：\n"
        "  KeyError: 'x'\n"
        "  frames:\n"
        "    app/store.py:5           get_by_id   <- 业务代码\n"
        "        return STORE[key]\n"
        f"  fingerprint: {fingerprint}\n"
        "  → 直接 read_file app/store.py 第 5 行附近，不要重新全仓 grep。"
    )


async def _call(mw: DebugLoopMiddleware, content, tool_name: str = "terminal"):
    request = SimpleNamespace(
        tool_call={"name": tool_name, "id": "call_1", "args": {}}
    )

    async def handler(_request):
        return ToolMessage(
            content=content,
            tool_call_id="call_1",
            name=tool_name,
            status="error",
        )

    return await mw.awrap_tool_call(request, handler)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# --- 计数与提示 --------------------------------------------------------------


def test_first_failure_is_silent():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    result = _run(_call(mw, _content()))
    assert ctx.debug_state == {_FP: 1}
    assert "[调试收敛]" not in result.content
    assert ctx.debug_halt is False


def test_second_failure_injects_retry_guidance():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    _run(_call(mw, _content()))
    result = _run(_call(mw, _content()))
    assert ctx.debug_state == {_FP: 2}
    assert _REPEAT_NOTE in result.content
    assert ctx.debug_halt is False
    # 原有内容必须完整保留——只追加，不替换。
    assert "[诊断]" in result.content


def test_third_failure_halts_and_asks_for_report():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    for _ in range(2):
        _run(_call(mw, _content()))
    result = _run(_call(mw, _content()))
    assert ctx.debug_state == {_FP: 3}
    assert ctx.debug_halt is True
    assert _HALT_NOTE in result.content
    assert "停止自动重试" in result.content
    assert "如实汇报" in result.content


def test_after_halt_no_further_injection():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    for _ in range(3):
        _run(_call(mw, _content()))
    assert ctx.debug_halt is True
    result = _run(_call(mw, _content()))
    # 已刹车：不再追加提示，避免在模型汇报前反复刷屏。
    assert "[调试收敛]" not in result.content
    assert ctx.debug_state == {_FP: 3}


def test_counting_is_shared_across_tools():
    """同一个 bug 换个工具跑也必须累计——旧 tool_name 去重挡不住的就是这条。"""
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    _run(_call(mw, _content(), tool_name="terminal"))
    result = _run(_call(mw, _content(), tool_name="run_tests"))
    assert ctx.debug_state == {_FP: 2}
    assert _REPEAT_NOTE in result.content


def test_different_fingerprints_counted_separately():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    _run(_call(mw, _content("111111111111")))
    result = _run(_call(mw, _content("222222222222")))
    assert ctx.debug_state == {"111111111111": 1, "222222222222": 1}
    assert "[调试收敛]" not in result.content
    assert ctx.debug_halt is False


# --- 成功路径与异常形态 ------------------------------------------------------


def test_success_path_untouched():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    result = _run(_call(mw, "测试全部通过：12 个通过"))
    assert result.content == "测试全部通过：12 个通过"
    assert ctx.debug_state == {}
    assert ctx.debug_halt is False


def test_failure_without_fingerprint_untouched():
    """无栈帧可解析的失败（纯 exit code 1）不计数、不注入，行为与改动前一致。"""
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    result = _run(_call(mw, "命令执行失败\nexit code 1"))
    assert "[调试收敛]" not in result.content
    assert ctx.debug_state == {}


def test_non_tool_message_result_is_ignored():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    request = SimpleNamespace(tool_call={"name": "terminal", "id": "c", "args": {}})

    async def handler(_request):
        return "not a ToolMessage"

    assert _run(mw.awrap_tool_call(request, handler)) == "not a ToolMessage"
    assert ctx.debug_state == {}


def test_list_content_is_ignored_without_crashing():
    ctx = _ctx()
    mw = DebugLoopMiddleware(ctx)
    blocks = [{"type": "text", "text": f"指纹 fingerprint: {_FP}"}]
    result = _run(_call(mw, blocks))
    # 多模态块形态不改写，也不会炸。
    assert result.content == blocks
    assert ctx.debug_state == {}


# --- 中间件链位置 ------------------------------------------------------------


def test_build_agent_registers_debug_loop_before_tool_error(monkeypatch):
    """§4.3：必须排在 ToolErrorMiddleware **之前**（= 更外层），
    否则异常还没被格式化成 ToolMessage，计数拿不到指纹。"""
    import app.agent.tools.tools as tools_mod

    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(tools_mod, "create_agent", fake_create_agent)
    ctx = _ctx()
    tools_mod._build_agent(llm=object(), tools=[], ctx=ctx)

    names = [type(m).__name__ for m in captured["middleware"]]
    assert "DebugLoopMiddleware" in names
    assert names.index("DebugLoopMiddleware") < names.index("ToolErrorMiddleware")
    assert names.index("TodoSyncMiddleware") < names.index("DebugLoopMiddleware")
