from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.terminal_policy import terminal_command_policy  # noqa: E402

_MAX_TIMEOUT = 600
_STDOUT_TAIL = 16_000
_STDERR_TAIL = 8_000


def _tail(text: str, limit: int) -> tuple[str, bool, int]:
    if not text:
        return "", False, 0
    truncated = len(text) > limit
    return text[-limit:], truncated, len(text)


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    command = str(params.get("command") or "").strip()
    if not command:
        print(json.dumps({"success": False, "message": "命令不能为空"}))
        return

    if terminal_command_policy(command) == "block":
        print(
            json.dumps(
                {"success": False, "message": "命令包含高危操作，已阻止"},
                ensure_ascii=False,
            )
        )
        return

    cwd_raw = params.get("cwd") or ""
    cwd = Path(cwd_raw).resolve() if cwd_raw else workspace
    if not cwd.is_dir():
        print(json.dumps({"success": False, "message": f"目录不存在: {cwd}"}))
        return
    try:
        timeout = max(1, min(int(params.get("timeout") or 30), _MAX_TIMEOUT))
    except (TypeError, ValueError):
        timeout = 30
    env = os.environ.copy()
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("PYTHONUNBUFFERED", "1")

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"success": False, "message": f"命令执行超时（{timeout}s）"}))
        return
    except OSError as exc:
        print(json.dumps({"success": False, "message": f"命令执行失败: {exc}"}))
        return

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    stdout_tail, stdout_truncated, stdout_bytes = _tail(stdout, _STDOUT_TAIL)
    stderr_tail, stderr_truncated, stderr_bytes = _tail(stderr, _STDERR_TAIL)
    content = stdout_tail
    if stderr_tail:
        content += ("\n" if content else "") + stderr_tail
    duration = round(time.time() - started, 3)
    print(
        json.dumps(
            {
                "success": True,
                "message": "命令执行完成",
                "stdout": stdout_tail,
                "stderr": stderr_tail,
                "exit_code": completed.returncode,
                "duration": duration,
                "content": content,
                "data": {
                    "cwd": str(cwd),
                    "exit_code": completed.returncode,
                    "duration": duration,
                    "timeout": timeout,
                    "stdout_bytes": stdout_bytes,
                    "stderr_bytes": stderr_bytes,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    # 供 run_tests/lint_check 等命令型工具做结构化解析
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
