from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.terminal_policy import terminal_command_policy  # noqa: E402


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
    timeout = int(params.get("timeout") or 30)
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
    content = stdout[-100_000:]
    if stderr:
        content += ("\n" if content else "") + stderr[-20_000:]
    print(
        json.dumps(
            {
                "success": True,
                "message": "命令执行完成",
                "stdout": stdout[-100_000:],
                "stderr": stderr[-20_000:],
                "exit_code": completed.returncode,
                "duration": round(time.time() - started, 3),
                "content": content[-100_000:],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
