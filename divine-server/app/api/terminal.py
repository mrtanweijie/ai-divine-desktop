from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..tools.terminal_policy import terminal_command_policy

router = APIRouter(prefix="/api", tags=["terminal"])

_ACTIVE_PROCS: set[int] = set()
_PENDING_TERMINAL: dict[str, dict[str, Any]] = {}


def create_terminal_decision(session_id: str) -> dict[str, Any]:
    pending: dict[str, Any] = {"event": asyncio.Event(), "allowed": None}
    _PENDING_TERMINAL[session_id] = pending
    return pending


def remove_terminal_decision(session_id: str) -> None:
    _PENDING_TERMINAL.pop(session_id, None)


class TerminalDecision(BaseModel):
    session_id: str
    allow: bool


async def wait_for_terminal_decision(
    session_id: str, command: str, timeout: int = 180
) -> bool:
    pending = create_terminal_decision(session_id)
    try:
        await asyncio.wait_for(pending["event"].wait(), timeout)
    except asyncio.TimeoutError:
        return False
    finally:
        remove_terminal_decision(session_id)
    return bool(pending["allowed"])


def _spawn_shell() -> tuple[int, subprocess.Popen[bytes]]:
    import pty

    master_fd, slave_fd = pty.openpty()
    shell = os.environ.get("SHELL") or "/bin/bash"
    if not os.path.exists(shell):
        shell = "/bin/bash"
    command = [shell]
    if shell.endswith(("bash", "zsh")):
        command.append("-l")
    env = os.environ.copy()
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("COLORTERM", "truecolor")
    proc = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave_fd)
    os.set_blocking(master_fd, False)
    return master_fd, proc


def _kill_process(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except OSError:
            pass


def _reader(
    master_fd: int,
    proc: subprocess.Popen[bytes],
    queue: asyncio.Queue[bytes | None],
    loop: asyncio.AbstractEventLoop,
) -> None:
    while True:
        try:
            data = os.read(master_fd, 65536)
        except BlockingIOError:
            if proc.poll() is not None:
                break
            time.sleep(0.01)
            continue
        except OSError:
            break
        if not data:
            break
        loop.call_soon_threadsafe(queue.put_nowait, data)
    loop.call_soon_threadsafe(queue.put_nowait, None)


def _resize(master_fd: int, cols: int, rows: int) -> None:
    import fcntl
    import struct
    import termios

    try:
        fcntl.ioctl(
            master_fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", int(rows), int(cols), 0, 0),
        )
    except OSError:
        pass


async def _send_loop(
    websocket: WebSocket, queue: asyncio.Queue[bytes | None]
) -> None:
    while True:
        data = await queue.get()
        if data is None:
            break
        try:
            await websocket.send_bytes(data)
        except Exception:
            break


def shutdown_terminal() -> None:
    for pid in list(_ACTIVE_PROCS):
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    _ACTIVE_PROCS.clear()
    for pending in _PENDING_TERMINAL.values():
        pending["allowed"] = False
        pending["event"].set()
    _PENDING_TERMINAL.clear()


@router.post("/terminal/decide")
async def decide_terminal(request: TerminalDecision) -> dict[str, Any]:
    pending = _PENDING_TERMINAL.get(request.session_id)
    if not pending:
        return {"ok": False, "message": "没有待确认的终端命令"}
    pending["allowed"] = request.allow
    pending["event"].set()
    return {"ok": True, "allow": request.allow}


@router.websocket("/terminal")
async def terminal_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    if os.name != "posix":
        await websocket.send_json(
            {"type": "error", "message": "交互式终端目前仅支持 macOS/Linux"}
        )
        await websocket.close()
        return

    try:
        master_fd, proc = _spawn_shell()
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json(
            {"type": "error", "message": f"终端启动失败: {exc}"}
        )
        await websocket.close()
        return

    _ACTIVE_PROCS.add(proc.pid)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    reader_task = asyncio.create_task(
        asyncio.to_thread(_reader, master_fd, proc, queue, loop)
    )
    writer_task = asyncio.create_task(_send_loop(websocket, queue))

    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload: dict[str, Any] = json.loads(message)
            except json.JSONDecodeError:
                payload = {"input": message}
            if payload.get("type") == "resize":
                _resize(
                    master_fd,
                    int(payload.get("cols") or 80),
                    int(payload.get("rows") or 24),
                )
            elif "input" in payload:
                os.write(master_fd, str(payload["input"]).encode("utf-8"))
    except WebSocketDisconnect:
        pass
    finally:
        _kill_process(proc)
        _ACTIVE_PROCS.discard(proc.pid)
        try:
            os.close(master_fd)
        except OSError:
            pass
        queue.put_nowait(None)
        for task in (writer_task, reader_task):
            task.cancel()
        for task in (writer_task, reader_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
