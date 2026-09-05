"""共享测试夹具。

aiosqlite 的 worker 线程不是 daemon，checkpointer 连接不关闭会阻止
pytest 进程退出；凡测试中经由 run_agent/get_checkpointer 创建的
saver，测试结束后统一关闭（磁盘上的线程态保留）。
"""

import pytest


@pytest.fixture(autouse=True)
def _close_checkpointers():
    yield
    import asyncio

    from app.agent.core.checkpointer import close_checkpointers

    try:
        asyncio.run(close_checkpointers())
    except Exception:  # noqa: BLE001 — 清理失败不影响测试结果
        pass
