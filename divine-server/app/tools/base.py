from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import output_dir_for_workspace

logger = logging.getLogger("divine.tools")


class ToolExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        message_key: str | None = None,
        message_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message_key = message_key
        self.message_params = message_params


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
    message_key: str | None = None
    message_params: dict[str, Any] | None = None

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
            "messageKey": self.message_key,
            "messageParams": self.message_params,
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

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
    ) -> ToolResult:
        params = self.build_params(arguments or {})
        script = Path(__file__).resolve().parent / "scripts" / self.script_name
        if not script.exists():
            raise ToolExecutionError(f"脚本不存在: {self.script_name}")
        output_root = output_dir_for_workspace(workspace)
        payload = {
            "workspace": str(workspace.resolve()),
            "output_dir": str(output_root.resolve()),
            "params": params,
            "locale": locale or "zh-CN",
        }
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            None, self._run_subprocess, str(script), payload
        )
        return self._result_from_output(workspace, output, output_root)

    def _run_subprocess(self, script: str, payload: dict[str, Any]) -> dict[str, Any]:
        stdin_text = json.dumps(payload, ensure_ascii=False)
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--run-script", str(script)]
        else:
            command = [sys.executable, str(script)]
        try:
            completed = subprocess.run(
                command,
                input=stdin_text,
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
            logger.warning(
                "tool script failed script=%s returncode=%s detail=%s",
                script,
                completed.returncode,
                detail[-2000:],
            )
            raise ToolExecutionError(
                "工具执行失败，请重试",
                message_key="tool.actionFailed",
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            logger.warning(
                "tool script returned invalid json script=%s stdout=%s",
                script,
                (completed.stdout or "")[-2000:],
            )
            raise ToolExecutionError(
                "工具执行失败，请重试",
                message_key="tool.actionFailed",
            ) from exc

    def _result_from_output(
        self, workspace: Path, output: dict[str, Any], output_root: Path
    ) -> ToolResult:
        if not output.get("success"):
            raise ToolExecutionError(
                output.get("message", "工具执行失败"),
                message_key=output.get("messageKey")
                or output.get("message_key"),
                message_params=output.get("messageParams")
                or output.get("message_params"),
            )
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
                message_key=output.get("messageKey")
                or output.get("message_key"),
                message_params=output.get("messageParams")
                or output.get("message_params"),
            )
        filepath = Path(filepath_value)
        if not filepath.is_absolute():
            filepath = workspace / filepath
        filepath = filepath.resolve()
        workspace_root = workspace.resolve()
        if (
            not self.allow_external_paths
            and not _is_within(workspace_root, filepath)
            and not _is_within(output_root, filepath)
        ):
            raise ToolExecutionError("工具输出路径越界，已拒绝")
        if not filepath.exists():
            raise ToolExecutionError(f"工具产物不存在: {filepath.name}")
        download_url: str | None = None
        try:
            relative = filepath.relative_to(output_root)
            if (
                self.category
                and len(relative.parts) > 0
                and relative.parts[0] == self.category
            ):
                # API_BASE already contains /api; downloadUrl() prepends it.
                download_url = f"/files/{self.category}/{filepath.name}"
        except ValueError:
            download_url = None
        return ToolResult(
            success=True,
            message=output.get("message", "执行完成"),
            file_name=filepath.name,
            filepath=str(filepath),
            download_url=download_url,
            file_size=os.path.getsize(filepath),
            content=output.get("content"),
            data=output.get("data"),
            message_key=output.get("messageKey")
            or output.get("message_key"),
            message_params=output.get("messageParams")
            or output.get("message_params"),
        )
