from __future__ import annotations

import asyncio
import concurrent.futures
import io
import json
import os
import runpy
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import output_dir


class ToolExecutionError(RuntimeError):
    pass


_IN_PROCESS_TOOL_LOCK = threading.Lock()


def _run_script_in_process(
    script: Path, payload: dict[str, Any], timeout: int
) -> dict[str, Any]:
    stdin_text = json.dumps(payload, ensure_ascii=False)

    def execute() -> tuple[str, str]:
        with _IN_PROCESS_TOOL_LOCK:
            old_stdin, old_stdout, old_stderr = sys.stdin, sys.stdout, sys.stderr
            out = io.StringIO()
            err = io.StringIO()
            try:
                sys.stdin = io.StringIO(stdin_text)
                sys.stdout = out
                sys.stderr = err
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit:
                pass
            except Exception as exc:
                raise ToolExecutionError(f"工具脚本执行异常: {exc}") from exc
            finally:
                sys.stdin, sys.stdout, sys.stderr = old_stdin, old_stdout, old_stderr
            return out.getvalue(), err.getvalue()

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(execute)
    try:
        raw, stderr_text = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        executor.shutdown(wait=False)
        raise ToolExecutionError(f"工具执行超时（{timeout}s）") from exc
    executor.shutdown(wait=False)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        stderr_tail = (
            stderr_text.strip()[-200:] if stderr_text.strip() else ""
        )
        raise ToolExecutionError(
            "工具脚本未返回合法 JSON: "
            + raw[-200:]
            + (f"；stderr: {stderr_tail}" if stderr_tail else "")
        ) from exc


@dataclass
class ToolResult:
    success: bool
    message: str
    file_name: str | None = None
    filepath: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    content: str | None = None
    data: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "file_name": self.file_name,
            "filepath": self.filepath,
            "download_url": self.download_url,
            "file_size": self.file_size,
            "content": self.content,
            "data": self.data,
        }


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_external_path(workspace: Path, raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        return str(resolved)
    return None


class ToolAdapter:
    """Base class for local tool scripts.

    Subclasses only define script_name/category/timeout and build_params.
    Subprocess handling, JSON parsing, file validation and download URLs
    are handled here so tool authors never touch process code.
    """

    script_name: str = ""
    category: str = ""
    timeout: int = 30
    supports_progress: bool = False
    allow_external_paths: bool = False

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {}

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        return []

    async def run(self, workspace: Path, arguments: dict[str, Any]) -> ToolResult:
        params = self.build_params(arguments or {})
        script = Path(__file__).resolve().parent / "scripts" / self.script_name
        if not script.exists():
            raise ToolExecutionError(f"脚本不存在: {self.script_name}")
        payload = {
            "workspace": str(workspace.resolve()),
            "output_dir": str(output_dir().resolve()),
            "params": params,
        }
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            None, self._run_subprocess, str(script), payload
        )
        return self._result_from_output(workspace, output)

    def _run_subprocess(self, script: str, payload: dict[str, Any]) -> dict[str, Any]:
        if getattr(sys, "frozen", False):
            return _run_script_in_process(
                Path(script), payload, self.timeout
            )
        try:
            completed = subprocess.run(
                [sys.executable, script],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError(
                f"工具执行超时（{self.timeout}s）"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise ToolExecutionError(
                f"工具脚本退出码 {completed.returncode}: {detail[-500:]}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                "工具脚本未返回合法 JSON: " + (completed.stdout or "")[-200:]
            ) from exc

    def _result_from_output(
        self, workspace: Path, output: dict[str, Any]
    ) -> ToolResult:
        if not output.get("success"):
            raise ToolExecutionError(output.get("message", "工具执行失败"))
        filepath_value = output.get("filepath") or output.get("file_name")
        if not filepath_value:
            return ToolResult(
                success=True,
                message=output.get("message", "执行完成"),
                filepath=None,
                download_url=None,
                file_size=None,
                content=output.get("content"),
                data=output.get("data"),
            )
        filepath = Path(filepath_value)
        if not filepath.is_absolute():
            filepath = workspace / filepath
        filepath = filepath.resolve()
        workspace_root = workspace.resolve()
        output_root = output_dir().resolve()
        if (
            not self.allow_external_paths
            and not _is_within(workspace_root, filepath)
            and not _is_within(output_root, filepath)
        ):
            raise ToolExecutionError("工具输出路径越界，已拒绝")
        if not filepath.exists():
            raise ToolExecutionError(f"工具产物不存在: {filepath.name}")
        return ToolResult(
            success=True,
            message=output.get("message", "执行完成"),
            file_name=filepath.name,
            filepath=str(filepath),
            download_url=None,
            file_size=os.path.getsize(filepath),
            content=output.get("content"),
            data=output.get("data"),
        )
