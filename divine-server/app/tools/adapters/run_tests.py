from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..command_output import parse_test_output
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


def _detect_runner(cwd: Path) -> str:
    """Detect the test runner for a project directory."""
    python_markers = (
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "conftest.py",
    )
    has_python_tests = any(cwd.glob("tests/*.py")) or any(
        cwd.glob("test_*.py")
    )
    if any((cwd / marker).exists() for marker in python_markers) or (
        has_python_tests
    ):
        return "pytest"
    package_json = cwd / "package.json"
    if package_json.exists():
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        deps = {
            **(manifest.get("dependencies") or {}),
            **(manifest.get("devDependencies") or {}),
        }
        if "vitest" in deps:
            return "vitest"
        if "jest" in deps:
            return "jest"
        if "test" in (manifest.get("scripts") or {}):
            return "npm_test"
    raise ToolExecutionError(
        "无法自动识别测试框架；请通过 runner 参数指定 pytest/jest/vitest/npm_test，"
        "或用 command 参数显式给出完整测试命令"
    )


def _runner_command(runner: str, paths: list[str], extra: str) -> str:
    target = f" {quote_paths(paths)}" if paths else ""
    suffix = f" {extra}" if extra else ""
    if runner == "pytest":
        return f"python3 -m pytest{target} --tb=short -q{suffix}"
    if runner == "vitest":
        return f"npx vitest run{target}{suffix}"
    if runner == "jest":
        return f"npx jest{target}{suffix}"
    if runner == "npm_test":
        return f"npm test{suffix}"
    raise ToolExecutionError(
        f"不支持的 runner: {runner}（可选 pytest/jest/vitest/npm_test）"
    )


def _build_command(cwd: Path | None, arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("command") or "").strip()
    if explicit:
        return explicit
    raw_paths = [str(p) for p in (arguments.get("paths") or [])]
    extra = str(arguments.get("extra_args") or "").strip()
    runner = str(arguments.get("runner") or "auto").strip()
    if cwd is None:
        # 审批预览：无 workspace 上下文，按声明的 runner 粗略构建。
        if runner == "auto":
            return "(run_tests 自动识别后执行)"
        return _runner_command(runner, raw_paths, extra)
    paths = existing_paths(cwd, raw_paths)
    if runner == "auto":
        runner = _detect_runner(cwd)
    return _runner_command(runner, paths, extra)


@register_tool(
    "run_tests",
    "运行项目的自动化测试并返回结构化结果（失败用例列表 + 通过/失败计数），"
    "比用 terminal 手跑更省上下文。支持 pytest / jest / vitest / npm test；"
    "默认自动识别项目类型，也可用 runner 指定、command 显式覆盖完整命令。"
    "执行与 terminal 走同一安全策略，需要确认时会先征求用户同意。"
    "输出只保留失败摘要，需要完整日志时再用 terminal。",
    {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "要测试的文件/目录（相对 cwd），例如 [\"tests/\"] 或 "
                    "[\"tests/test_api.py::test_login\"]；留空测整个项目"
                ),
            },
            "runner": {
                "type": "string",
                "enum": ["auto", "pytest", "jest", "vitest", "npm_test"],
                "description": "测试框架，auto 为自动识别",
                "default": "auto",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（workspace 内相对路径），默认 workspace 根",
            },
            "extra_args": {
                "type": "string",
                "description": "附加命令行参数，如 -k login",
            },
            "command": {
                "type": "string",
                "description": "显式指定完整测试命令（优先于 runner 自动构建）",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数 60-600，默认 180；大型套件请给足",
                "default": 180,
            },
        },
    },
)
class RunTestsAdapter(ToolAdapter):
    category = "system"
    timeout = 180

    def build_command(self, arguments: dict[str, Any]) -> str:
        """Command string for the approval gate (no filesystem validation)."""
        return _build_command(None, arguments or {})

    def effective_timeout(self, arguments: dict[str, Any]) -> int:
        return clamp_timeout(arguments or {}, default=180)

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
            detected_runner = _detect_runner(cwd)
        except ToolExecutionError:
            detected_runner = str(scoped.get("runner") or "unknown")
        result = await run_via_terminal(workspace, scoped, command, timeout)
        stdout, stderr, exit_code = extract_command_output(result)
        parsed = parse_test_output(f"{stdout}\n{stderr}", detected_runner)
        counts = parsed.get("counts") or {}
        passed = int(counts.get("passed", 0))
        failed = int(counts.get("failed", 0))
        success = bool(result.success) and exit_code == 0 and failed == 0
        if failed:
            message = f"测试失败：{failed} 个失败，{passed} 个通过"
        elif success and parsed["parsed"]:
            message = f"测试全部通过：{passed} 个通过"
        elif success:
            message = "测试完成（未能解析输出，详见 content）"
        else:
            message = f"测试未通过：{parsed.get('summary') or '见原始输出'}"
        return ToolResult(
            success=success,
            message=message,
            content=build_content_summary(
                "测试结果",
                str(parsed.get("summary") or ""),
                parsed["items"],
                stdout[-2000:] if not parsed["parsed"] else "",
            ),
            data={
                "command": command,
                "cwd": str(cwd),
                "exit_code": exit_code,
                "runner": detected_runner,
                "parsed": parsed["parsed"],
                "summary": parsed.get("summary"),
                "counts": counts,
                "failures": parsed["items"],
            },
        )
