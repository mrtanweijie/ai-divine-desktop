"""Git tool script: status / diff / log / commit / revert.

Reads JSON from stdin with params:
- action: status | diff | log | commit | revert
- path: optional workspace-relative path to scope the operation
- staged: for diff, compare the index instead of the working tree
- ref: for diff, base ref (default HEAD)
- message: commit message (required for commit)
- n: number of log entries (default 10)

All git invocations use argument lists (no shell) so command injection is
impossible. Write operations (commit/revert) are gated at the agent level by
user confirmation before this script runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_git(workspace: Path, args: list[str], timeout: int = 30) -> dict:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"git 执行超时（{timeout}s）"}
    except OSError as exc:
        return {"success": False, "message": f"git 执行失败: {exc}"}
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        detail = (stderr or stdout).strip()
        if (
            "not a git repository" in detail
            or "不是 Git 仓库" in detail
            or "不是git仓库" in detail
        ):
            return {
                "success": False,
                "message": "当前工作区不是 git 仓库（或未初始化）",
            }
        return {
            "success": False,
            "message": f"git 命令失败: {detail[-500:]}",
            "data": {"stdout": stdout[-4000:], "stderr": stderr[-4000:]},
        }
    return {
        "success": True,
        "stdout": stdout,
        "stderr": stderr,
        "content": stdout,
    }


def _action_status(workspace: Path, params: dict) -> dict:
    args = ["status", "--short", "--branch"]
    path = str(params.get("path") or "").strip()
    if path:
        args.append("--")
        args.append(path)
    result = _run_git(workspace, args)
    if not result.get("success"):
        return result
    lines = [line for line in (result.get("stdout") or "").splitlines() if line]
    # Branch header ("## main") is not a change; anything else indicates changes.
    changes = [line for line in lines if not line.startswith("##")]
    return {
        "success": True,
        "message": f"git status：{len(lines)} 行",
        "content": result.get("stdout") or "（工作区干净，无改动）",
        "data": {"lines": lines, "clean": not changes},
    }


def _action_diff(workspace: Path, params: dict) -> dict:
    ref = str(params.get("ref") or "").strip()
    if params.get("staged"):
        args = ["diff", "--staged"]
    elif ref:
        args = ["diff", ref]
    else:
        args = ["diff"]
    path = str(params.get("path") or "").strip()
    if path:
        args.append("--")
        args.append(path)
    result = _run_git(workspace, args)
    if not result.get("success"):
        return result
    diff = result.get("stdout") or ""
    if not diff.strip():
        return {"success": True, "message": "无改动（diff 为空）", "content": "", "data": {"empty": True}}
    return {
        "success": True,
        "message": f"git diff：{len(diff.splitlines())} 行",
        "content": diff,
        "data": {"diff": diff, "empty": False},
    }


def _action_log(workspace: Path, params: dict) -> dict:
    try:
        n = max(1, min(int(params.get("n") or 10), 100))
    except (TypeError, ValueError):
        n = 10
    result = _run_git(workspace, ["log", "--oneline", "-n", str(n)])
    if not result.get("success"):
        return result
    output = result.get("stdout") or ""
    return {
        "success": True,
        "message": f"最近 {len([l for l in output.splitlines() if l])} 条提交",
        "content": output,
    }


def _action_commit(workspace: Path, params: dict) -> dict:
    message = str(params.get("message") or "").strip()
    if not message:
        return {"success": False, "message": "commit 需要 message 参数"}
    add = _run_git(workspace, ["add", "-A"])
    if not add.get("success"):
        return add
    commit = _run_git(workspace, ["commit", "-m", message])
    if not commit.get("success"):
        return commit
    output = commit.get("stdout") or ""
    return {
        "success": True,
        "message": "已提交",
        "content": output,
        "data": {"commit": output.strip()},
    }


def _action_revert(workspace: Path, params: dict) -> dict:
    path = str(params.get("path") or "").strip()
    if path:
        result = _run_git(workspace, ["restore", "--", path])
    else:
        # Revert all uncommitted changes of tracked files; untracked files are
        # left untouched (removing them would risk data loss).
        result = _run_git(workspace, ["restore", "."])
    if not result.get("success"):
        return result
    return {
        "success": True,
        "message": (
            "已还原" + (f" {path}" if path else "所有已跟踪文件的未提交改动（未跟踪文件保留）")
        ),
        "content": result.get("stdout") or "已还原",
    }


_ACTIONS = {
    "status": _action_status,
    "diff": _action_diff,
    "log": _action_log,
    "commit": _action_commit,
    "revert": _action_revert,
}


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    action = str(params.get("action") or "").strip()
    handler = _ACTIONS.get(action)
    if handler is None:
        print(
            json.dumps(
                {"success": False, "message": f"未知 git action: {action}"},
                ensure_ascii=False,
            )
        )
        return
    result = handler(workspace, params)
    result.setdefault("data", {})["action"] = action
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
