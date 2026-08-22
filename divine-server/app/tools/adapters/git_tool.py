from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool

_GIT_WRITE_ACTIONS = {"commit", "revert"}


class _GitBaseAdapter(ToolAdapter):
    """Shared adapter for git tools; subclasses set the action."""

    script_name = "git_tool.py"
    category = "system"
    timeout = 30
    action = "status"

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": self.action,
            "path": str(arguments.get("path") or "").strip(),
            "staged": bool(arguments.get("staged")),
            "ref": str(arguments.get("ref") or "").strip(),
            "message": str(arguments.get("message") or ""),
            "n": arguments.get("n"),
        }


@register_tool(
    "git_status",
    "查看 git 仓库状态（git status --short --branch）：显示当前分支、已修改/未跟踪/暂存的文件。"
    "修改文件前先调用本工具了解工作区状态，path 可限定查看某个文件/目录。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "workspace 内相对路径，限定查看范围，可选",
            }
        },
    },
)
class GitStatusAdapter(_GitBaseAdapter):
    action = "status"


@register_tool(
    "git_diff",
    "查看未提交的改动（unified diff），用于在编辑后自查修改是否符合预期；"
    "支持查看暂存区（staged=true）或与某个 ref 的差异。返回完整 diff 文本。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "workspace 内相对路径，只看该路径的改动，可选",
            },
            "staged": {
                "type": "boolean",
                "description": "是否查看已暂存（git add 后）的改动，默认 false",
                "default": False,
            },
            "ref": {
                "type": "string",
                "description": "对比的基准 ref，如 HEAD~1、某个提交 hash，默认与工作区对比",
            },
        },
    },
)
class GitDiffAdapter(_GitBaseAdapter):
    action = "diff"


@register_tool(
    "git_log",
    "查看最近提交历史（git log --oneline），了解项目最近改动，n 为条数。",
    {
        "type": "object",
        "properties": {
            "n": {
                "type": "integer",
                "description": "最近几条提交，默认 10，最大 100",
                "default": 10,
            }
        },
    },
)
class GitLogAdapter(_GitBaseAdapter):
    action = "log"


@register_tool(
    "git_commit",
    "提交当前所有改动（git add -A 后 git commit）：需要用户确认后执行，message 为提交说明。"
    "只在用户要求提交/保存进度时使用，不要擅自提交。",
    {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "提交说明",
            }
        },
        "required": ["message"],
    },
)
class GitCommitAdapter(_GitBaseAdapter):
    action = "commit"


@register_tool(
    "git_revert",
    "还原未提交的改动（git restore）：还原单个文件时传 path，不传 path 则还原工作区所有未提交改动。"
    "编辑出错需要回滚时使用；执行前需要用户确认。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要还原的 workspace 内相对路径；不传则还原全部未提交改动",
            }
        },
    },
)
class GitRevertAdapter(_GitBaseAdapter):
    action = "revert"


def is_git_write_action(name: str) -> bool:
    return name in {"git_commit", "git_revert"}


__all__ = [
    "GitStatusAdapter",
    "GitDiffAdapter",
    "GitLogAdapter",
    "GitCommitAdapter",
    "GitRevertAdapter",
    "is_git_write_action",
]
