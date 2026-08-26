from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..command_output import parse_lint_output
from ..registry import register_tool
from .command_support import (
    build_content_summary,
    clamp_timeout,
    existing_paths,
    extract_command_output,
    quote_paths,
    resolve_cwd,
    run_via_terminal,
)

_LINTERS = ("ruff", "mypy", "eslint", "tsc")


def _detect_linter(cwd: Path) -> str:
    has_python = any(cwd.glob("*.py")) or (cwd / "pyproject.toml").exists()
    if (cwd / "tsconfig.json").exists():
        return "tsc"
    if any(cwd.glob(".eslintrc*")) or (cwd / "eslint.config.js").exists():
        return "eslint"
    if has_python:
        return "ruff"
    raise ToolExecutionError(
        "无法自动识别 linter；请通过 linter 参数指定 ruff/mypy/eslint/tsc，"
        "或用 command 参数显式给出完整命令"
    )


def _linter_command(linter: str, paths: list[str], extra: str) -> str:
    target = f" {quote_paths(paths)}" if paths else ""
    suffix = f" {extra}" if extra else ""
    if linter == "ruff":
        return f"python3 -m ruff check{target}{suffix or ' --output-format=concise'}"
    if linter == "mypy":
        return f"python3 -m mypy{target}{suffix}"
    if linter == "tsc":
        # tsc 不接受文件参数与 --noEmit 混用时的项目模式，固定全项目检查。
        return f"npx tsc --noEmit{suffix}"
    if linter == "eslint":
        return f"npx eslint{target or ' .'}{suffix}"
    raise ToolExecutionError(
        f"不支持的 linter: {linter}（可选 ruff/mypy/eslint/tsc）"
    )


def _build_command(cwd: Path | None, arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("command") or "").strip()
    if explicit:
        return explicit
    raw_paths = [str(p) for p in (arguments.get("paths") or [])]
    extra = str(arguments.get("extra_args") or "").strip()
    linter = str(arguments.get("linter") or "auto").strip()
    if cwd is None:
        if linter == "auto":
            return "(lint_check 自动识别后执行)"
        return _linter_command(linter, raw_paths, extra)
    paths = existing_paths(cwd, raw_paths)
    if linter == "auto":
        linter = _detect_linter(cwd)
    return _linter_command(linter, paths, extra)


@register_tool(
    "lint_check",
    "对代码运行静态检查并返回结构化问题列表（file:line + 规则码 + 信息），"
    "比用 terminal 手跑更省上下文。支持 ruff / mypy / eslint / tsc；"
    "默认按项目类型自动识别，也可用 linter 参数指定、command 显式覆盖完整命令。"
    "执行与 terminal 走同一安全策略。编辑代码后建议先跑本工具再跑测试。",
    {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "要检查的文件/目录（相对 cwd），例如 [\"src/\"]；留空查整个项目"
                ),
            },
            "linter": {
                "type": "string",
                "enum": ["auto", "ruff", "mypy", "eslint", "tsc"],
                "description": "静态检查工具，auto 为自动识别",
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
                "description": "显式指定完整检查命令（优先于 linter 自动构建）",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数 60-600，默认 120",
                "default": 120,
            },
        },
    },
)
class LintCheckAdapter(ToolAdapter):
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
            detected = _detect_linter(cwd)
        except ToolExecutionError:
            detected = str(scoped.get("linter") or "unknown")
        result = await run_via_terminal(workspace, scoped, command, timeout)
        stdout, stderr, exit_code = extract_command_output(result)
        parsed = parse_lint_output(f"{stdout}\n{stderr}", detected)
        counts = parsed.get("counts") or {}
        errors = int(counts.get("errors", 0))
        success = bool(result.success) and exit_code == 0 and errors == 0
        if errors:
            message = f"发现 {errors} 个问题（详见 content）"
        elif success and parsed["parsed"]:
            message = "未发现问题"
        elif exit_code == 0:
            message = "检查完成，未报告问题"
        else:
            message = "检查未通过：见原始输出"
        return ToolResult(
            success=success,
            message=message,
            content=build_content_summary(
                "检查结果",
                str(parsed.get("summary") or ""),
                parsed["items"],
                (stdout + "\n" + stderr)[-2500:] if not parsed["parsed"] else "",
            ),
            data={
                "command": command,
                "cwd": str(cwd),
                "exit_code": exit_code,
                "linter": detected,
                "parsed": parsed["parsed"],
                "summary": parsed.get("summary"),
                "counts": counts,
                "issues": parsed["items"],
            },
        )
