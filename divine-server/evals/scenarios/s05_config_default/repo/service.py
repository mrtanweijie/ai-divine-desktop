"""HTTP 调用封装（本地模拟，不发真实请求）。"""

import config


def call_remote(url: str, timeout: int | None = None) -> dict:
    """Simulate a remote call. timeout=None 时应使用 config.DEFAULT_TIMEOUT。"""
    if timeout is None:
        timeout = 10
    return {"url": url, "timeout": timeout, "status": 200}
