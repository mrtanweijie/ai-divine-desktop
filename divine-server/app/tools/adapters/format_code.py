from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from .command_support import (
    clamp_timeout,
    existing_paths,
    quote_paths,
    resolve_cwd,
    run_via_terminal,
)

_FORMATTERS = ("ruff", "prettier")


def _detect_formatter(cwd: Path) -> str:
    web_files = any(
        cwd.glob(f"src/**/*.{ext}")
        for ext in ("ts", "tsx", "js", "jsx", "vue", "css")
    )
    if (cwd / "package.json").exists() and web_files:
        return "prettier"
    if any(cwd.glob("*.py")) or (cwd / "pyproject.toml").exists():
        return "ruff"
    raise ToolExecutionError(
        "无法自动识别格式化工具；请通过 formatter 参数指定 ruff/prettier，"
        "或用 command 参数显式给出完整命令"
    )


def _formatter_command(formatter: str, paths: list[str], extra: str) -> str:
    target = f" {quote_paths(paths)}" if paths else ""
    suffix = f" {extra}" if extra else ""
    if formatter == "ruff":
        return f"python3 -m ruff format{target}{suffix}"
    if formatter == "prettier":
        return f"npx prettier --write{target or ' .'}{suffix}"
    raise ToolExecutionError(
        f"不支持的 formatter: {formatter}（可选 ruff/prettier）"
    )


def _build_command(cwd: Path | None, arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("command") or "").strip()
    if explicit:
        return explicit
    raw_paths = [str(p) for p in (arguments.get("paths") or [])]
    extra = str(arguments.get("extra_args") or "").strip()
    formatter = str(arguments.get("formatter") or "auto").strip()
    if cwd is None:
        if formatter == "auto":
            return "(format_code 自动识别后执行)"
        return _formatter_command(formatter, raw_paths, extra)
    paths = existing_paths(cwd, raw_paths)
    if formatter == "auto":
        formatter = _detect_formatter(cwd)
    return _formatter_command(formatter, paths, extra)


def _count_changed(stdout: str) -> int | None:
    """ruff format prints 'N files reformatted'; prettier prints per-file."""
    for line in stdout.splitlines():
        line = line.strip()
        for prefix in (
            "files reformatted",
            "file reformatted",
            "files left unchanged",
            "1 file left unchanged",
        ):
            if line.endswith(prefix):
                try:
                    count = int(line.split(" ", 1)[0])
                except ValueError:
                    continue
                if "unchanged" in prefix:
                    return 0
                return count
    return None


@register_tool(
    "format_code",
    "对代码文件运行格式化（ruff format / prettier --write 自动识别），原地修改文件并返回变更统计；"
    "也可用 formatter 指定工具、command 显式覆盖完整命令。执行与 terminal 走同一安全策略。"
    "编辑代码后建议先 format 再 lint_check / run_tests。",
    {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "要格式化的文件/目录（相对 cwd），例如 [\"src/\"]；留空处理整个项目"
                ),
            },
            "formatter": {
                "type": "string",
                "enum": ["auto", "ruff", "prettier"],
                "description": "格式化工具，auto 为自动识别",
                "default": "auto",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（workspace 内相对路径），默认 workspace 根",
            },
            "extra_args": {
                "type": "string",
                "description": "附加命令行参数",
            },
            "command": {
                "type": "string",
                "description": "显式指定完整格式化命令（优先于 formatter 自动构建）",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数 60-600，默认 120",
                "default": 120,
            },
        },
    },
)
class FormatCodeAdapter(ToolAdapter):
    category = "system"
    timeout = 120

    def build_command(self, arguments: dict[str, Any]) -> str:
        """Command string for the approval gate (no filesystem validation)."""
        return _build_command(None, arguments or {})

    def effective_timeout(self, arguments: dict[str, Any]) -> int:
        return clamp_timeout(arguments or {}, default=120)

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        del locale, progress_callback
        cwd = resolve_cwd(workspace, arguments)
        timeout = self.effective_timeout(arguments)
        scoped = {**arguments, "cwd": str(cwd)}
        command = _build_command(cwd, scoped)
        try:
            detected = _detect_formatter(cwd)
        except ToolExecutionError:
            detected = str(scoped.get("formatter") or "unknown")
        result = await run_via_terminal(workspace, scoped, command, timeout)
        data = result.data or {}
        stdout = str(data.get("stdout_tail") or "")
        stderr = str(data.get("stderr_tail") or "")
        exit_code = int(data.get("exit_code") or 0)
        success = bool(result.success) and exit_code == 0
        changed = _count_changed(f"{stdout}\n{stderr}")
        if not success:
            message = f"格式化失败：{(stderr or stdout)[-300:]}"
        elif changed is None:
            message = "格式化完成"
        elif changed == 0:
            message = "格式化完成：没有文件需要改动"
        else:
            message = f"格式化完成：{changed} 个文件被重新格式化"
        return ToolResult(
            success=success,
            message=message,
            content=(stdout + ("\n" + stderr if stderr else "")).strip()[-2000:]
            or None,
            data={
                "command": command,
                "cwd": str(cwd),
                "exit_code": exit_code,
                "formatter": detected,
                "changed": changed,
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            },
        )
