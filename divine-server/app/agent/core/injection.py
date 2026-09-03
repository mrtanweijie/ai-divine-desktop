"""用户插话（steering）注入队列。

执行中的 agent run 通过 UserInjectionMiddleware 在每次模型调用前
drain 本队列，把用户主动补充的信息注入 state。与 `_CANCEL_EVENTS`
同模式：进程内 dict，单 sidecar 进程内端点与图运行共享。

约定：drain 即消费即删除（同一条插话最多注入一次）；run 收尾由
调用方 discard 兜底，消息本体已在落库时持久化，不会丢失。
"""

from __future__ import annotations

# 每 session 未消费插话上限，超过直接拒绝（防止刷屏堆积）
MAX_PENDING_INJECTIONS = 5
# 单条插话长度上限（字符）
MAX_CONTENT_LENGTH = 4000

# 标记前缀：落库与注入消息共用，前端据此渲染"补充"气泡样式
SUPPLEMENT_PREFIX = "[用户补充]"

_INJECT_QUEUES: dict[str, list[str]] = {}


def enqueue_injection(session_id: str, content: str) -> bool:
    """入队一条插话；队满返回 False。"""
    queue = _INJECT_QUEUES.setdefault(session_id, [])
    if len(queue) >= MAX_PENDING_INJECTIONS:
        return False
    queue.append(content)
    return True


def drain_injections(session_id: str) -> list[str]:
    """取走并清空该 session 的全部待消费插话。"""
    return _INJECT_QUEUES.pop(session_id, [])


def discard_injections(session_id: str) -> None:
    """丢弃全部待消费插话（run 收尾兜底：消息已落库，防跨 run 泄漏）。"""
    _INJECT_QUEUES.pop(session_id, None)


def pending_count(session_id: str) -> int:
    """当前待消费插话数（测试与端点校验用）。"""
    return len(_INJECT_QUEUES.get(session_id, []))
