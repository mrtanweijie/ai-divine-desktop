"""Background process manager for the agent's terminal tool.

Long-running commands (dev servers, builds, watch tasks) are started with
``terminal(background=true)`` and managed through ``bg_status`` / ``bg_output``
/ ``bg_kill``. Processes live in the FastAPI sidecar process, are scoped by
session, buffer their output in memory (ring buffer), and are killed on
application shutdown.

This module runs in-process (not as a tool subprocess script) because the
processes must outlive a single tool call.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("divine.tools.bg")

_BUFFER_BYTES_LIMIT = 64 * 1024
_BUFFER_LINES_LIMIT = 2000
_OUTPUT_TAIL_DEFAULT = 16_000


@dataclass
class BackgroundProcess:
    bg_id: str
    session_id: str
    command: str
    cwd: str
    created_at: float
    process: asyncio.subprocess.Process | None = None
    status: str = "starting"  # starting | running | exited | killed | failed
    exit_code: int | None = None
    error: str | None = None
    _buffer: deque[str] = field(default_factory=deque)
    _buffer_bytes: int = 0
    _readers: list[asyncio.Task] = field(default_factory=list)

    def append_output(self, text: str) -> None:
        if not text:
            return
        self._buffer.append(text)
        self._buffer_bytes += len(text)
        while (
            self._buffer_bytes > _BUFFER_BYTES_LIMIT
            or len(self._buffer) > _BUFFER_LINES_LIMIT
        ):
            dropped = self._buffer.popleft()
            self._buffer_bytes -= len(dropped)

    def tail_output(self, max_chars: int = _OUTPUT_TAIL_DEFAULT) -> tuple[str, bool, int]:
        text = "".join(self._buffer)
        truncated = len(text) > max_chars
        return text[-max_chars:], truncated, self._buffer_bytes

    def summary(self) -> dict[str, Any]:
        return {
            "bg_id": self.bg_id,
            "session_id": self.session_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "exit_code": self.exit_code,
            "created_at": round(self.created_at, 1),
            "running_seconds": round(time.time() - self.created_at, 1),
        }

    async def stop(self) -> None:
        """Terminate, then kill after a grace period. Best-effort."""
        proc = self.process
        if proc is None or proc.returncode is not None:
            self.status = "killed" if self.status not in ("exited", "failed") else self.status
            return
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        except (ProcessLookupError, OSError):
            pass
        self.status = "killed"
        for reader in self._readers:
            reader.cancel()


class BackgroundProcessManager:
    def __init__(self) -> None:
        self._processes: dict[str, BackgroundProcess] = {}

    async def start(
        self,
        session_id: str,
        command: str,
        cwd: str,
        env: dict[str, str] | None = None,
    ) -> BackgroundProcess:
        bg = BackgroundProcess(
            bg_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            command=command,
            cwd=cwd,
            created_at=time.time(),
        )
        self._processes[bg.bg_id] = bg
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        proc_env.setdefault("LANG", "en_US.UTF-8")
        proc_env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=proc_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            bg.status = "failed"
            bg.error = str(exc)
            logger.warning("bg start failed session=%s command=%s: %s", session_id, command, exc)
            return bg
        bg.process = proc
        bg.status = "running"

        async def _drain(stream: asyncio.StreamReader | None, prefix: str = "") -> None:
            assert stream is not None
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    bg.append_output(prefix + line.decode("utf-8", errors="replace"))
            except (asyncio.CancelledError, ConnectionResetError):
                pass

        if proc.stdout is not None:
            bg._readers.append(asyncio.create_task(_drain(proc.stdout)))
        if proc.stderr is not None:
            bg._readers.append(asyncio.create_task(_drain(proc.stderr, prefix="")))
        asyncio.create_task(self._wait_exit(bg))
        logger.info("bg started session=%s bg_id=%s command=%s", session_id, bg.bg_id, command)
        return bg

    async def _wait_exit(self, bg: BackgroundProcess) -> None:
        assert bg.process is not None
        try:
            code = await bg.process.wait()
        except asyncio.CancelledError:
            return
        bg.exit_code = code
        bg.status = "exited"
        for reader in bg._readers:
            reader.cancel()
        logger.info("bg exited bg_id=%s code=%s", bg.bg_id, code)

    def get(self, bg_id: str, session_id: str | None = None) -> BackgroundProcess | None:
        bg = self._processes.get(bg_id)
        if bg is None:
            return None
        if session_id and bg.session_id != session_id:
            return None
        return bg

    def list_for_session(self, session_id: str) -> list[BackgroundProcess]:
        return [
            proc
            for proc in self._processes.values()
            if proc.session_id == session_id
        ]

    async def kill(self, bg_id: str, session_id: str | None = None) -> BackgroundProcess | None:
        bg = self.get(bg_id, session_id)
        if bg is None:
            return None
        await bg.stop()
        logger.info("bg killed session=%s bg_id=%s", session_id, bg_id)
        return bg

    async def shutdown_all(self) -> None:
        for bg in list(self._processes.values()):
            await bg.stop()
        self._processes.clear()
        logger.info("bg manager shutdown: all processes stopped")


bg_manager = BackgroundProcessManager()
