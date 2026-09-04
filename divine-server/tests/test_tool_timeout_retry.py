"""工具超时自动重试测试（幂等只读工具）。

覆盖：
- 可重试工具（web_search）首次超时 → 自动重试 → on_retry 回调 1 次
- 两次都超时 → 返回超时错误，tool_run 落 error + 总耗时
- 非白名单工具（terminal）超时不重试，on_retry 不被调用
- 第二次成功 → 返回成功结果，duration 覆盖两次 attempt
"""


def _init(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app import db

    db.init_db()
    return db


class _SlowAdapter:
    """run() 永远超时的假 adapter。"""

    timeout = 0.02

    async def run(self, workspace, arguments, locale=None, progress_callback=None):
        import asyncio

        await asyncio.sleep(1)


class _FlakyAdapter:
    """第一次超时、第二次立即成功的假 adapter。"""

    timeout = 0.02

    def __init__(self):
        self.calls = 0

    async def run(self, workspace, arguments, locale=None, progress_callback=None):
        import asyncio

        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(1)
        from app.tools.base import ToolResult

        return ToolResult(
            success=True, message="ok", data={"value": 1}, content=""
        )


def test_retryable_tool_retries_then_succeeds(monkeypatch, tmp_path):
    import asyncio

    from app.agent.tools.tool_runtime import _execute_tool

    db = _init(monkeypatch, tmp_path)
    session = db.create_session("重试测试", None)
    retries: list[int] = []

    async def on_retry(attempt):
        retries.append(attempt)

    output = asyncio.run(
        _execute_tool(
            session["id"],
            _FlakyAdapter(),
            "web_search",
            {"query": "x"},
            tmp_path,
            run_meta={},
            turn=1,
            on_retry=on_retry,
        )
    )
    assert output["success"] is True
    assert retries == [1]
    run = db.list_tool_runs(session["id"])[0]
    assert run["status"] == "done"
    assert run["turn"] == 1
    assert run["duration_ms"] is not None and run["duration_ms"] > 0


def test_retryable_tool_gives_up_after_max_attempts(monkeypatch, tmp_path):
    import asyncio

    from app.agent.tools.tool_runtime import _execute_tool

    db = _init(monkeypatch, tmp_path)
    session = db.create_session("重试放弃测试", None)
    retries: list[int] = []

    async def on_retry(attempt):
        retries.append(attempt)

    output = asyncio.run(
        _execute_tool(
            session["id"],
            _SlowAdapter(),
            "web_search",
            {"query": "x"},
            tmp_path,
            run_meta={},
            on_retry=on_retry,
        )
    )
    assert output["success"] is False
    assert "超时" in output["message"]
    assert retries == [1]
    run = db.list_tool_runs(session["id"])[0]
    assert run["status"] == "error"
    assert run["duration_ms"] >= 40


def test_non_retryable_tool_does_not_retry(monkeypatch, tmp_path):
    import asyncio

    from app.agent.tools.tool_runtime import _execute_tool

    db = _init(monkeypatch, tmp_path)
    session = db.create_session("不重试测试", None)
    retries: list[int] = []

    async def on_retry(attempt):
        retries.append(attempt)

    output = asyncio.run(
        _execute_tool(
            session["id"],
            _SlowAdapter(),
            "terminal",
            {"command": "x"},
            tmp_path,
            run_meta={},
            on_retry=on_retry,
        )
    )
    assert output["success"] is False
    assert retries == []
    run = db.list_tool_runs(session["id"])[0]
    assert run["status"] == "error"
