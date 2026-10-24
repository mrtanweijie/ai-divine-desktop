"""一次性密钥把手存储（032 §5 密钥把手模式）。

登录卡片前端把密码直存到这里（POST /api/browser/secrets），返回一次性把手
（``secret:<hex>``）。agent 只见把手、不见明文——密码不进对话上下文、
不发给云端模型、不落日志。引擎填入时解析并立即销毁（一次性）。
进程内存存储：重启即失效（TTL 10 分钟），刻意不持久化。
"""

from __future__ import annotations

import logging
import secrets as _secrets
import time

logger = logging.getLogger("divine.browser.secrets")

_TTL_SECONDS = 600
_store: dict[str, tuple[str, float]] = {}


def store_secret(value: str) -> str:
    """存入明文，返回一次性把手。"""
    handle = f"secret:{_secrets.token_hex(8)}"
    _store[handle] = (value, time.time())
    # 顺带清理过期项
    now = time.time()
    expired = [k for k, (_, ts) in _store.items() if now - ts > _TTL_SECONDS]
    for k in expired:
        _store.pop(k, None)
    return handle


def resolve_secret(handle: str) -> str | None:
    """解析把手并立即销毁（一次性）；无效/过期返回 None。"""
    item = _store.pop(handle, None)
    if item is None:
        return None
    value, ts = item
    if time.time() - ts > _TTL_SECONDS:
        return None
    return value


def clear_all() -> None:
    _store.clear()
