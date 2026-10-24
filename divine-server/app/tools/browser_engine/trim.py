"""快照历史裁剪（031 §4「快照只保留最新一份」）。

browser 子 agent 的历史里，旧快照/截图工具结果替换为一行占位符（保留 URL 行
供模型定位），只保留最新 keep 条完整结果——多步任务的快照 token 不再随步数
线性膨胀。与全局上下文 stub 窗口（docs/review/011 C2）互补：C2 管主对话，
本中间件只针对 browser 子 agent 的快照类结果。
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

_STUB_MARK = "[旧快照已丢弃，仅保留最新一份]"


class BrowserSnapshotTrimMiddleware(AgentMiddleware):
    """每次模型调用前，把历史中较旧的 browser 快照结果替换为占位符。"""

    def __init__(self, browser_tools: frozenset[str], keep: int = 1) -> None:
        super().__init__()
        self._browser_tools = browser_tools
        self._keep = max(1, keep)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        messages = getattr(request, "messages", None)
        if not messages:
            return await handler(request)

        # tool_call_id → 工具名（从 AIMessage.tool_calls 建立映射）
        id_to_name: dict[str, str] = {}
        for msg in messages:
            for tc in getattr(msg, "tool_calls", None) or []:
                name = str(tc.get("name") or "")
                tid = str(tc.get("id") or "")
                if name in self._browser_tools and tid:
                    id_to_name[tid] = name
        if not id_to_name:
            return await handler(request)

        # 倒序找出 browser 工具的 ToolMessage；只保留最新 keep 条
        browser_ids: list[str] = []
        for msg in messages:
            tid = getattr(msg, "tool_call_id", None)
            if tid and tid in id_to_name:
                browser_ids.append(tid)
        if len(browser_ids) <= self._keep:
            return await handler(request)
        to_stub = set(browser_ids[:-self._keep])

        stubbed = 0
        for msg in messages:
            tid = getattr(msg, "tool_call_id", None)
            if tid not in to_stub:
                continue
            content = msg.content if isinstance(msg.content, str) else ""
            if not content:
                continue
            url_line = next(
                (ln for ln in content.splitlines() if ln.startswith("URL:")), ""
            )
            msg.content = f"{_STUB_MARK} {url_line}".strip()
            stubbed += 1
        if stubbed:
            return await handler(request)
        return await handler(request)
