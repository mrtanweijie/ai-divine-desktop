"""主线程 / 事件循环阻塞点隔离的回归测试（plan 005）。

分两节：

A. ``LocalLLMManager`` 操作锁（方案 §5「最容易被忽略的坑」）
   ``start`` / ``stop`` / ``uninstall_model`` 原先靠**事件循环天然串行化**，
   搬到线程池（``asyncio.to_thread``）后就能并发执行，必须显式加锁。这里用
   并发探针验证互斥性、用「start 内部会调 stop」验证锁必须可重入，并锁定
   ``install_model`` 有意不加锁这一设计。

B. 路由卸载（B1 / B3 / B5）
   事件循环被同步调用冻住时，在途 SSE 流会**静默挂死**（无输出、无错误、
   无超时），极难排查。这里用「期间循环还能跑多少个 tick」当可观测指标：
   被冻住时 tick 停在 0~1，正确卸载到线程池时应接近 ``block_s / 0.01``。
"""

from __future__ import annotations

import asyncio
import os
import signal
import threading
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------- A. 操作锁


class _ConcurrencyProbe:
    """并发探针：撑开一个窗口，窗口内出现第二个进入者即记为并发违规。

    以「最坏情况」构造：一旦有人单独进入就睡 ``window`` 秒，给并发的第二个
    调用留出足够的进入机会。若外层没有串行化，``max_active`` 必然 > 1。
    """

    def __init__(self, window: float = 0.3) -> None:
        self._mu = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.calls = 0
        self.window = window

    def __call__(self, *args: object, **kwargs: object) -> None:
        with self._mu:
            self._active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(self.window)
        with self._mu:
            self._active -= 1


def _new_manager(tmp_path: Path):
    from app.agent.core.local_llm import LocalLLMManager

    # port=0：本测试不会真的 spawn 进程，端口只是构造参数
    return LocalLLMManager(str(tmp_path), port=0)


def test_serialized_decorator_coverage():
    """只有 start / stop / uninstall_model 走操作锁。

    三条是「碰进程句柄与模型文件」的操作；``install_model`` /
    ``install_custom_model`` / ``register_local_model`` 是分钟级下载或大文件
    复制，持锁会把 ``stop_model`` 一起卡住，所以**有意**不加。
    """
    from app.agent.core.local_llm import LocalLLMManager

    for name in ("start", "stop", "uninstall_model"):
        assert hasattr(getattr(LocalLLMManager, name), "__wrapped__"), (
            f"{name} 必须加 @_serialized：搬到线程池后不再有事件循环天然串行化"
        )
    for name in ("install_model", "install_custom_model", "register_local_model"):
        assert not hasattr(getattr(LocalLLMManager, name), "__wrapped__"), (
            f"{name} 不应加 @_serialized：长耗时的下载/复制持锁会卡死 stop"
        )


def test_start_stop_uninstall_are_mutually_exclusive(tmp_path, monkeypatch):
    """§5：三个操作并发触发时，同一时刻只能有一个在跑。"""
    from app.agent.core import local_llm

    manager = _new_manager(tmp_path)
    probe = _ConcurrencyProbe()
    # start / stop 都会走到 _free_orphan_port；uninstall_model 走 delete_model。
    # 两者共用同一个探针，才能覆盖跨操作的互斥。
    monkeypatch.setattr(manager, "_free_orphan_port", probe)
    monkeypatch.setattr(manager, "_find_binary", lambda: None)
    monkeypatch.setattr(
        local_llm, "delete_model", lambda model_id, models_dir: probe()
    )

    barrier = threading.Barrier(3)

    def _wrap(fn):
        def _target() -> None:
            barrier.wait(timeout=5)
            fn()

        return _target

    threads = [
        threading.Thread(
            target=_wrap(lambda: manager.start("m", str(tmp_path / "missing.gguf"))),
            daemon=True,
        ),
        threading.Thread(target=_wrap(manager.stop), daemon=True),
        threading.Thread(
            target=_wrap(lambda: manager.uninstall_model("m")), daemon=True
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads), "操作锁未串行化，出现挂起"
    assert probe.calls == 3, "三个操作都应各自执行一次"
    assert probe.max_active == 1, (
        f"操作锁失效：探针观测到 {probe.max_active} 个并发进入者"
    )


class _FakeProc:
    """``stop()`` 只用到 ``pid`` / ``wait()``；``poll()`` 返回 None 表示仍在运行。"""

    def __init__(self) -> None:
        self.pid = 4242
        self.waited = False

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0

    def terminate(self) -> None:  # Windows 分支
        self.waited = True

    def kill(self) -> None:  # pragma: no cover — 走到这里说明 killpg 分支异常
        raise AssertionError("stop() 不应退到 kill 分支")


def test_start_reenters_stop_without_deadlock(tmp_path, monkeypatch):
    """§5：``start()`` 内部会调 ``stop()``，所以操作锁必须是可重入的。

    若锁不可重入（普通 ``Lock``），这条路径会直接死锁——而它只在「切换模型」
    时才走到，手工点几次「启动」是测不出来的。
    """
    from app.agent.core import local_llm

    manager = _new_manager(tmp_path)
    proc = _FakeProc()
    manager.process = proc  # type: ignore[assignment]
    manager.active_model_id = "old"

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(local_llm.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        local_llm.os, "killpg", lambda pgid, sig: killed.append((pgid, sig))
    )
    monkeypatch.setattr(manager, "_free_orphan_port", lambda *a, **k: None)
    monkeypatch.setattr(manager, "_find_binary", lambda: None)

    box: list[object] = []
    thread = threading.Thread(
        target=lambda: box.append(
            manager.start("new", str(tmp_path / "missing.gguf"))
        ),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive(), "操作锁不可重入：start() 内部的 stop() 死锁"
    assert proc.waited, "start() 没有先停掉旧进程"
    assert manager.process is None
    assert manager.active_model_id is None
    if os.name != "nt":
        assert killed == [(4242, signal.SIGTERM)]
    assert box == [(False, "llama-server 二进制文件未找到")]


def test_install_model_does_not_hold_the_op_lock(tmp_path, monkeypatch):
    """设计锁定：分钟级下载不能持操作锁，否则 ``stop_model`` 被一起卡住。"""
    from app.agent.core import local_llm

    manager = _new_manager(tmp_path)
    inside = threading.Event()
    release = threading.Event()

    def _slow_download(model_id, models_dir, progress):
        inside.set()
        release.wait(timeout=15)
        return None  # 下载失败 → install_model 返回 False

    monkeypatch.setattr(local_llm, "download_model", _slow_download)
    monkeypatch.setattr(manager, "_free_orphan_port", lambda *a, **k: None)

    installer = threading.Thread(
        target=manager.install_model, args=("m",), daemon=True
    )
    installer.start()
    assert inside.wait(timeout=5), "install_model 没有进入下载"

    # 下载仍在进行中，stop() 必须能立刻拿到操作锁
    stopper = threading.Thread(target=manager.stop, daemon=True)
    try:
        stopper.start()
        stopper.join(timeout=10)
        assert not stopper.is_alive(), "install_model 持有了操作锁，stop() 被下载卡住"
    finally:
        release.set()
        installer.join(timeout=10)
    assert not installer.is_alive()


# ------------------------------------------------- B. 路由卸载（tick 可观测）


def _ticks_while(factory, block_s: float = 0.3) -> int:
    """跑 ``factory()`` 协程，返回期间事件循环还能执行多少个 10ms tick。

    调用方阻塞事件循环时 tick 会停在 0~1（第一个 sleep 已被调度但跑不到）；
    正确卸载到线程池时应接近 ``block_s / 0.01``。
    """

    async def _run() -> int:
        ticks = 0

        async def _ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(_ticker())
        try:
            await factory()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return ticks

    return asyncio.run(_run())


def _assert_offloaded(ticks: int, label: str, block_s: float = 0.3) -> None:
    expected = block_s / 0.01
    assert ticks >= expected / 3, (
        f"{label} 阻塞了事件循环：{block_s}s 内只跑了 {ticks} 个 tick"
        f"（正确卸载时应接近 {expected:.0f}）"
    )


class _StubSettings:
    """避免路由测试碰到真实配置文件。"""

    def load(self) -> dict:
        return {}

    def save(self, settings: dict) -> None:
        pass


def test_local_llm_stop_route_offloads_manager_stop(monkeypatch):
    """B3：``POST /local_llm/stop`` 里 ``manager.stop`` 固定 ≥3s，必须卸载。"""
    from app.api import local_llm as api

    stopped: list[bool] = []

    class _SlowManager:
        def stop(self) -> None:
            time.sleep(0.3)
            stopped.append(True)

    monkeypatch.setattr(api, "settings_store", _StubSettings())
    monkeypatch.setattr("app.agent.core.get_manager", lambda: _SlowManager())

    ticks = _ticks_while(api.stop_model)
    assert stopped == [True], "stop_model 没有调用 manager.stop"
    _assert_offloaded(ticks, "local_llm.stop_model → manager.stop")


def test_local_llm_status_route_offloads_get_status(monkeypatch):
    """B3：``GET /local_llm/status`` 内含多个 subprocess.run，必须卸载。"""
    from app.api import local_llm as api

    class _SlowManager:
        def get_status(self) -> dict:
            time.sleep(0.3)
            return {
                "installed_models": [],
                "recommended_models": [],
                "custom_models": [],
                "download_progress": {},
            }

    monkeypatch.setattr("app.agent.core.get_manager", lambda: _SlowManager())

    ticks = _ticks_while(api.get_status)
    _assert_offloaded(ticks, "local_llm.get_status → manager.get_status")


def test_compact_route_offloads_db_and_breakdown(monkeypatch):
    """B5：``sessions.compact_session`` 是本文件唯一的 async 路由。

    其余路由是同步 ``def``，FastAPI 自己会放进线程池——**不能**改成
    ``async def``（不补 ``to_thread`` 就等于把阻塞搬到事件循环上）。

    两处阻塞分开量：只让一个慢，才能确定是哪一个被卸载了。
    """
    from app.agent import state as state_module
    from app.api import sessions as api

    delays = {"db": 0.0, "breakdown": 0.0}

    class _SlowDb:
        def get_session(self, session_id: str) -> dict:
            time.sleep(delays["db"])
            return {"id": session_id, "title": "t"}

    async def _fake_compact(session_id: str) -> dict:
        return {"summary": "结论：方案 A。", "saved_tokens": 7}

    def _slow_breakdown(session_id: str) -> dict:
        time.sleep(delays["breakdown"])
        return {"used": 1, "limit": 2}

    monkeypatch.setattr(api, "db", _SlowDb())
    monkeypatch.setattr(state_module, "compact_session", _fake_compact)
    monkeypatch.setattr(state_module, "build_context_breakdown", _slow_breakdown)

    result: dict = {}

    async def _capture() -> None:
        result["value"] = await api.compact_session("s1")

    asyncio.run(_capture())
    assert result["value"]["compacted"] is True
    assert result["value"]["usage"] == {"used": 1, "limit": 2}

    delays["db"] = 0.3
    delays["breakdown"] = 0.0
    ticks = _ticks_while(lambda: api.compact_session("s1"))
    _assert_offloaded(ticks, "sessions.compact_session → db.get_session")

    delays["db"] = 0.0
    delays["breakdown"] = 0.3
    ticks = _ticks_while(lambda: api.compact_session("s1"))
    _assert_offloaded(ticks, "sessions.compact_session → build_context_breakdown")


# ------------------------------------------- B1. 自动拉起本地模型的时长上界


class _FakeClock:
    """只替换 ``preprocess`` 模块里的 ``time``，不动全局 time 模块。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _NeverReadyManager:
    """``start()`` 声称成功但永不就绪——模拟最坏路径（进程在、端口不通）。"""

    def __init__(self) -> None:
        self.process = object()  # 非 None：不触发「快速失败」分支
        self.ready_calls = 0

    def get_status(self) -> dict:
        return {"installed_models": [{"id": "m", "path": "/tmp/m.gguf"}]}

    def start(self, model_id: str, path: str, wait_s: float = 3.0):
        return True, ""

    def is_ready(self) -> bool:
        self.ready_calls += 1
        return False


def test_start_local_model_polling_cap_is_20s(monkeypatch):
    """B1：轮询上限 20s（不是 40s）——它就是调用方 ``to_thread`` 的时长上界。

    ``manager.start`` 内部已等 ``wait_s=10s``，再叠 40s 会让最坏路径到 50s，
    期间那个线程池工作线程一直被占着。
    """
    from app.agent.middleware import preprocess

    clock = _FakeClock()
    monkeypatch.setattr(preprocess, "time", clock)
    monkeypatch.setattr("app.config.settings_store", _StubSettings())

    manager = _NeverReadyManager()
    started = clock.now
    assert preprocess._start_local_model(manager) is False
    elapsed = clock.now - started

    assert clock.slept == [2.0] * 10, (
        f"轮询节奏变了：期望 10 次 × 2s，实际 {clock.slept}"
    )
    assert elapsed == 20.0, f"轮询上限被放大到 {elapsed}s（应为 20s）"
    assert manager.ready_calls == 10


def test_start_local_model_returns_false_without_models(monkeypatch):
    """无已装模型时立刻降级云端，不进轮询。"""
    from app.agent.middleware import preprocess

    class _NoModelManager:
        def get_status(self) -> dict:
            return {"installed_models": []}

    clock = _FakeClock()
    monkeypatch.setattr(preprocess, "time", clock)

    assert preprocess._start_local_model(_NoModelManager()) is False
    assert clock.slept == []


# ------------------------------------------- 静态兜底：卸载清单不许被悄悄删掉


def _dotted(node) -> str:
    """把 ``a.b.c`` 形式的表达式还原成点分字符串；其它返回 ""。"""
    import ast

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    return ""


def _to_thread_targets(path: Path) -> set[str]:
    """收集文件里所有 ``asyncio.to_thread(X, ...)`` 的第一个参数名。"""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _dotted(node.func) not in ("asyncio.to_thread", "to_thread"):
            continue
        name = _dotted(node.args[0])
        if name:
            targets.add(name)
    return targets


# plan 005 逐个落地的卸载点。只做「至少还剩一处」的粗粒度兜底：精确的
# 行为验证在文件上半部分（tick 与并发探针）。这里的作用是，万一有人把
# 某个 to_thread 改回裸调用，能在几毫秒内红一次，不必靠人眼 diff。
_EXPECTED_OFFLOADS: dict[str, set[str]] = {
    "app/api/chat.py": {
        "_read_text_fallback",  # B4 附件正文回退读取
        "_start_local_model",  # B1 自动拉起本地模型（最长 20s）
        "db.get_session",  # B5
        "db.history_for_model",  # B5
        "db.session_workspace",  # B5
        "db.touch_session",  # B5
        "read_file_text",  # B4 PDF/Word/Excel 同步解析
    },
    "app/api/sessions.py": {
        "build_context_breakdown",  # B5 CPU 型 token 估算
        "db.get_session",  # B5
    },
    "app/api/local_llm.py": {
        "detect_hardware",  # B3 subprocess.run
        "manager.get_status",  # B3
        "manager.stop",  # B3（内部固定 ≥3s）
        "manager.uninstall_model",  # B3
    },
    "app/agent/tools/execution.py": {
        "syntax_check_paths",  # B2 py_compile 子进程
    },
}


@pytest.mark.parametrize("name", sorted(_EXPECTED_OFFLOADS))
def test_expected_blocking_calls_stay_offloaded(name: str):
    """plan 005 的卸载点不许被改回裸调用。"""
    root = Path(__file__).resolve().parents[1]
    actual = _to_thread_targets(root / name)
    missing = _EXPECTED_OFFLOADS[name] - actual
    assert not missing, (
        f"{name} 缺少 to_thread 卸载：{sorted(missing)}；"
        "事件循环被同步调用冻住会让在途 SSE 流静默挂死"
    )


# --------------------------------------- C. 端到端：真实 ASGI 栈上的可用性探针


def test_health_stays_responsive_while_manager_stop_runs(tmp_path, monkeypatch):
    """§7.1 端到端：阻塞操作进行中，`GET /api/health` 仍要 ≤几百 ms。

    前面几节的 tick 测试是在「裸协程」上量的；这一条走**完整 ASGI 栈**
    （TestClient + 真实路由 + 中间件），更贴近用户体感：事件循环被冻住时，
    在途 SSE 流会静默挂死，`/api/health` 也会一起超时。

    `manager.stop()` 内部固定等 `_free_orphan_port(wait_s=3.0)`，这里用
    一个睡 2s 的桩代替，不真起/杀进程。
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "probe.db"))
    from app import db

    db.init_db()

    class _SlowManager:
        def stop(self) -> None:
            time.sleep(2.0)

    from app.api import local_llm as api

    monkeypatch.setattr(api, "settings_store", _StubSettings())
    monkeypatch.setattr("app.agent.core.get_manager", lambda: _SlowManager())

    from app.main import app

    with TestClient(app) as test_client:
        latencies: list[float] = []
        finished = threading.Event()

        def _stop() -> None:
            try:
                test_client.post("/api/local_llm/stop")
            finally:
                finished.set()

        worker = threading.Thread(target=_stop, daemon=True)
        worker.start()
        # 一直采到 stop 结束**且**至少 3 个样本：冻住时第一次探测就要 2s，
        # 若只采到一次就退出，下面会退化成「样本太少」这种看不出原因的报错。
        while not finished.is_set() or len(latencies) < 3:
            if len(latencies) >= 200:
                break
            started = time.perf_counter()
            test_client.get("/api/health")
            latencies.append(time.perf_counter() - started)
            time.sleep(0.02)
        worker.join(timeout=15)

    assert latencies, "一次探测都没做成"
    worst = max(latencies)
    assert worst < 1.0, (
        f"/api/health 最差 {worst:.2f}s——事件循环被 manager.stop 冻住了；"
        f"全部样本 {[round(v, 3) for v in latencies]}"
    )
