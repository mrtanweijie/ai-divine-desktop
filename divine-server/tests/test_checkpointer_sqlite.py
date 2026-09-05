"""主代理 checkpointer 持久化：线程态落到 ai_workspace.db 同目录的
checkpoints.db，sidecar 重启后 aget_state 仍有内容（不再每轮 DB 重建
+ 全量 tool_calls 修复）。"""

import asyncio


def test_get_checkpointer_same_instance_per_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai_workspace.db"))
    from app.agent.core.checkpointer import get_checkpointer

    async def run():
        from app.agent.core.checkpointer import close_checkpointers

        saver1 = await get_checkpointer()
        saver2 = await get_checkpointer()
        assert saver1 is saver2
        await close_checkpointers()
        return saver1

    saver = asyncio.run(run())
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    assert isinstance(saver, AsyncSqliteSaver)
    assert (tmp_path / "checkpoints.db").exists()


def test_get_checkpointer_new_loop_gets_fresh_instance(tmp_path, monkeypatch):
    """aiosqlite 连接绑定创建它的循环：新循环（如 sidecar 重启后的新
    事件循环、测试用例）必须拿到新实例，不得复用旧循环的连接。"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai_workspace.db"))
    from app.agent.core.checkpointer import get_checkpointer

    async def run():
        from app.agent.core.checkpointer import close_checkpointers

        saver = await get_checkpointer()
        await close_checkpointers()
        return saver

    first = asyncio.run(run())
    second = asyncio.run(run())
    assert first is not second


def test_thread_state_survives_checkpointer_recreation(tmp_path, monkeypatch):
    """模拟 sidecar 重启：新事件循环重建 saver 后，aget_state 仍读到
    上一轮写入的线程态（InMemorySaver 时代这里恒为空）。"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai_workspace.db"))
    from langchain_core.messages import HumanMessage
    from langgraph.graph import START, MessagesState, StateGraph

    from app.agent.core.checkpointer import close_checkpointers, get_checkpointer

    def build_graph(saver):
        builder = StateGraph(MessagesState)
        builder.add_node(
            "chat", lambda state: {"messages": [("assistant", "收到")]}
        )
        builder.add_edge(START, "chat")
        return builder.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": "t1"}}

    async def run_turn():
        saver = await get_checkpointer()
        graph = build_graph(saver)
        await graph.ainvoke(
            {"messages": [HumanMessage(content="你好")]}, config
        )
        # 关闭连接等价进程重启：磁盘上的线程态保留，新连接可复元
        await close_checkpointers()

    async def read_state():
        saver = await get_checkpointer()
        graph = build_graph(saver)
        snapshot = await graph.aget_state(config)
        await close_checkpointers()
        return snapshot

    asyncio.run(run_turn())
    snapshot = asyncio.run(read_state())
    messages = (snapshot.values or {}).get("messages") or []
    assert [m.type for m in messages] == ["human", "ai"], (
        "重启后线程态必须保留（不再退回 DB 历史重建路径）"
    )
