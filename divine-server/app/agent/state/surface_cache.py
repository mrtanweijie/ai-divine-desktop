"""面板 IR 的进程内快照（按 tool_call_id）。

为什么需要：有些面板**无法从工具入参离线重建**——``fx_rates`` 的折线依赖联网取到的
日线序列，入参里只有币种和天数。回合收尾要落库时再调一次接口既慢又不稳定，
于是改为「发事件的那一刻顺手存一份 IR」，落库时按 ``call_id`` 取回。

生命周期与代价：
* 只在当前进程内有效（sidecar 重启即失效，面板不再出现在历史里）；
* 容量固定 128 条、FIFO 淘汰，单条 IR 已被上游限制在 200k 字符以内，
  最坏内存占用可控，不会随会话增长。

这不是缓存加速用的，**是保证「看到的」和「存下的」是同一块面板**。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

#: 同时保留的面板数。一个回合最多几块面板，128 足够覆盖最近的几十轮。
MAX_ENTRIES = 128

_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

#: 按工具名的「最后一次」兜底：``runtime.tool_call_id`` 在个别打包/子图场景下
#: 可能与 AIMessage 里的 call id 对不上，此时精确匹配会静默落空。宁可取同工具
#: 最近一块面板，也不要让用户「看到图、结束后没了」。
_LAST_BY_TOOL: dict[str, tuple[str, dict[str, Any]]] = {}


def remember(call_id: str, surface: Any, tool: str = "") -> None:
    """存一份面板 IR；``call_id`` 为空或形态不对时静默跳过。"""
    if not call_id or not isinstance(surface, dict) or not surface.get("surfaceId"):
        return
    _CACHE[call_id] = surface
    _CACHE.move_to_end(call_id)
    if tool:
        _LAST_BY_TOOL[tool] = (call_id, surface)
    while len(_CACHE) > MAX_ENTRIES:
        _CACHE.popitem(last=False)


def get(call_id: str, tool: str = "") -> dict[str, Any] | None:
    if call_id and call_id in _CACHE:
        surface = _CACHE[call_id]
        _CACHE.move_to_end(call_id)
        return surface
    if tool:
        entry = _LAST_BY_TOOL.get(tool)
        if entry:
            return entry[1]
    return None


def clear() -> None:
    """测试用。"""
    _CACHE.clear()
    _LAST_BY_TOOL.clear()
