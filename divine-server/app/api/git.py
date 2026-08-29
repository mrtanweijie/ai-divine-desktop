"""Git 项目信息 API：分支、ahead/behind、变更文件、最近提交、远程、stash。"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/git", tags=["git"])
logger = logging.getLogger("divine.git")


def _run_git(project_path: str, *args: str) -> str | None:
    """执行 git 命令，返回 stdout；失败返回 None。"""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def _parse_status(output: str) -> list[dict]:
    """解析 git status --porcelain=v1 输出为文件列表。

    格式：XY filename（两个状态字符 + 空格 + 文件名）
    重命名：XY orig -> new
    """
    files = []
    for line in output.splitlines():
        if len(line) < 3:
            continue
        index_status = line[0]
        work_status = line[1]
        # 文件名从第 3 个字符开始（索引 2）
        rest = line[2:].lstrip(" ")
        # 重命名格式：orig -> new，取 new 部分
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]

        # 优先用 work_status，其次 index_status
        code = work_status if work_status != " " else index_status
        status_map = {
            "M": "modified",
            "A": "added",
            "D": "deleted",
            "R": "renamed",
            "C": "added",
            "?": "untracked",
        }
        files.append({
            "path": rest,
            "status": status_map.get(code, "modified"),
        })
    return files


def _relative_time(timestamp_str: str) -> str:
    """将 git log 的相对时间规范化。"""
    # git log --format='%cr' 已经输出相对时间，直接返回
    return timestamp_str.strip()


@router.get("/info")
def git_info(path: str = Query(..., description="项目文件夹绝对路径")):
    """返回项目的 git 基本信息。"""
    project = Path(path).resolve()
    if not project.is_dir():
        raise HTTPException(status_code=400, detail="路径不存在")

    # 检测是否是 git 仓库
    git_dir = _run_git(str(project), "rev-parse", "--git-dir")
    if not git_dir:
        return {
            "is_git": False,
            "branch": "",
            "ahead": 0,
            "behind": 0,
            "dirty": False,
            "total_changes": 0,
            "files": [],
            "last_commit": None,
            "remote_url": "",
            "stash_count": 0,
        }

    # 分支名
    branch = _run_git(str(project), "branch", "--show-current") or "HEAD"

    # ahead / behind
    ahead, behind = 0, 0
    ahead_behind = _run_git(
        str(project), "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
    )
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    # 变更文件
    status_output = _run_git(str(project), "status", "--porcelain=v1") or ""
    logger.debug("git status raw: %r", status_output)
    files = _parse_status(status_output)
    logger.debug("git status parsed: %s", files)
    dirty = len(files) > 0

    # 最近提交
    last_commit = None
    log_output = _run_git(
        str(project), "log", "-1", "--format=%s||%cr"
    )
    if log_output and "||" in log_output:
        message, relative_time = log_output.split("||", 1)
        last_commit = {
            "message": message.strip(),
            "relative_time": _relative_time(relative_time),
        }

    # 远程地址
    remote_url = _run_git(str(project), "remote", "get-url", "origin") or ""

    # stash 数量
    stash_output = _run_git(str(project), "stash", "list")
    stash_count = len(stash_output.splitlines()) if stash_output else 0

    return {
        "is_git": True,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "total_changes": len(files),
        "files": files,
        "last_commit": last_commit,
        "remote_url": remote_url,
        "stash_count": stash_count,
    }
