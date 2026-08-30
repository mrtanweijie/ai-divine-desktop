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
_CWD_STATE_FILE = "terminal_cwd.json"


def _tail(text: str, limit: int) -> tuple[str, bool, int]:
    if not text:
        return "", False, 0
    truncated = len(text) > limit
    return text[-limit:], truncated, len(text)


def _cwd_state_file() -> Path | None:
    """会话级 cwd 状态文件（持久 shell 廉价版，仅 posix）。

    用 data_root()（读 DIVINE_DATA_DIR，与应用数据目录一致）；
    不要用 data_dir()——config 导入时会 setdefault DB_PATH，使 data_dir()
    在脚本子进程里固定解析到仓库内 DB 文件路径。
    """
    if os.name != "posix":
        return None
    try:
        from app.config import data_root

        state_dir = data_root()
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / _CWD_STATE_FILE
    except Exception:  # noqa: BLE001 — 状态不可用只影响记忆功能
        return None


def _read_cwd_state(state_file: Path | None) -> dict:
    if state_file is None:
        return {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_final_cwd(state_file: Path | None, session_id: str, state_tmp: Path) -> None:
    """把本条命令结束时 shell 的 $PWD 记入会话状态（尽力而为）。"""
    try:
        final_cwd = Path(state_tmp.read_text(encoding="utf-8").strip())
        if final_cwd.is_dir():
            state = _read_cwd_state(state_file)
            state[session_id] = str(final_cwd)
            assert state_file is not None
            state_file.write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            state_tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


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
    session_id = str(params.get("session_id") or "global")

    # --- 会话级 cwd 记忆：不显式传 cwd 时从上次命令结束的目录继续 ---
    state_file = _cwd_state_file()
    stored_cwd = _read_cwd_state(state_file).get(session_id)
    if not cwd_raw and stored_cwd and Path(stored_cwd).is_dir():
        cwd = Path(stored_cwd)
    else:
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

    # --- 命令结束时把 $PWD 落盘（仅 posix）：
    # 用换行分隔（不用子 shell 包裹——子 shell 里的 cd 透不出 $PWD），
    # $? 在下一条命令前取值即上一条命令的退出码，路径经环境变量传入避免转义。
    state_tmp: Path | None = None
    shell_command = command
    if state_file is not None:
        state_tmp = state_file.parent / f".terminal_cwd_{os.getpid()}.tmp"
        env["__divine_state"] = str(state_tmp)
        shell_command = (
            f"{command}\n"
            "__divine_exit=$?\n"
            'printf \'%s\' "$PWD" > "$__divine_state"\n'
            "exit $__divine_exit"
        )

    started = time.time()
    try:
        completed = subprocess.run(
            shell_command,
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
    finally:
        if state_tmp is not None:
            _save_final_cwd(state_file, session_id, state_tmp)

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    stdout_tail, stdout_truncated, stdout_bytes = _tail(stdout, _STDOUT_TAIL)
    stderr_tail, stderr_truncated, stderr_bytes = _tail(stderr, _STDERR_TAIL)
    content = stdout_tail
    if stderr_tail:
        content += ("\n" if content else "") + stderr_tail
    duration = round(time.time() - started, 3)
    final_cwd = _read_cwd_state(state_file).get(session_id) or str(cwd)
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
                    "final_cwd": final_cwd,
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
