"""LangGraph 线程态持久化：主代理使用 AsyncSqliteSaver 落盘线程态。

进程内存 checkpointer 在 sidecar 重启后丢失进行中会话的工具调用状态，
导致每轮都要 DB 历史重建 + 全量 tool_calls 修复，compact/上下文裁剪
策略也跨重启失效。线程态落到 ai_workspace.db 同目录的 checkpoints.db。

按事件循环懒加载单例：aiosqlite 连接绑定创建它的循环（生产为单个
uvicorn 循环；测试每个用例各自建循环，互不串扰）。子代理是一次性
任务，无需跨重启状态，保持 InMemorySaver 不落盘。
"""

import asyncio

# id(loop) -> (loop, saver)；校验 loop 身份防止 id 复用串扰
_SAVERS: dict[int, tuple[asyncio.AbstractEventLoop, object]] = {}
_LOCK = asyncio.Lock()


async def get_checkpointer():
    loop = asyncio.get_running_loop()
    entry = _SAVERS.get(id(loop))
    if entry is not None and entry[0] is loop:
        return entry[1]
    async with _LOCK:
        entry = _SAVERS.get(id(loop))
        if entry is not None and entry[0] is loop:
            return entry[1]
        from ...config import db_path
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = await aiosqlite.connect(str(db_path().parent / "checkpoints.db"))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        _SAVERS[id(loop)] = (loop, saver)
        return saver


async def close_checkpointers() -> None:
    """关闭并清空缓存的 saver 连接。

    aiosqlite 的 worker 线程不是 daemon，连接不关闭会阻止进程退出
    （pytest 收尾挂起 / sidecar 关停拖延），应用 shutdown 时必须调用。
    """
    for _loop, saver in list(_SAVERS.values()):
        try:
            conn = getattr(saver, "conn", None)
            if conn is not None:
                await conn.close()
        except Exception:  # noqa: BLE001 — 关停路径尽力而为
            pass
    _SAVERS.clear()
