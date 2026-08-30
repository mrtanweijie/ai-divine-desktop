"""自动 code review（P4-2）：把当前未提交改动交给 LLM 做只读审查。

一次 LLM 调用（不经过子 Agent 工具循环），输入 `git diff HEAD`（含暂存区），
输出按严重度排列的问题清单与修改建议。只读：不修改任何文件。

边界：
- 工作区不是 git 仓库 / diff 为空时直接返回提示；
- diff 超长截断保留头部（超限的改动建议用户分批提交审查）；
- untracked 新文件不在 `git diff HEAD` 里，结果中会提示。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool

_MAX_DIFF_CHARS = 60_000

_SYSTEM_PROMPT = (
    "你是严格的代码审查员。审查给出的 unified diff，只关注：\n"
    "1) 正确性 bug 与边界条件；2) 安全问题（注入/密钥泄漏/路径穿越）；\n"
    "3) 明显性能问题；4) 与改动目标无关的可疑变更。\n"
    "输出格式（简体中文，不超过 25 行）：\n"
    "- 每个问题一行：[严重/警告/建议] 文件:行号 — 问题说明 → 修改建议；\n"
    "- 没有问题时只输出一行：审查通过，未发现明显问题；\n"
    "- 不要复述 diff，不要夸奖代码。"
)


def build_review_prompt(diff: str, focus: str = "") -> str:
    parts = [f"以下是待审查的 unified diff（共 {len(diff)} 字符）：", "", diff]
    if focus:
        parts.append(f"\n用户特别要求关注：{focus}")
    return "\n".join(parts)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    return str(content or "")


async def _run_review(diff: str, focus: str) -> str:
    """单次 LLM 审查调用（模型用当前会话默认模型）。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from ...agent.core import _build_llm

    llm = _build_llm()
    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=build_review_prompt(diff, focus)),
        ]
    )
    review = _content_text(getattr(response, "content", "")).strip()
    if not review:
        raise ToolExecutionError("审查模型返回了空结果，请重试")
    return review


@register_tool(
    "review_changes",
    "对当前工作区未提交的代码改动做一次自动 code review：收集 git diff（含暂存区），"
    "交给审查模型输出问题清单（严重度/位置/建议）。只读工具，不修改文件。"
    "适用于改完代码后的自查；工作区需为 git 仓库。可选 focus 参数指定重点关注方向"
    "（如'并发安全'）。新建的未跟踪文件不在 diff 里，审查前建议先 git add。",
    {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "可选，重点关注方向，如：并发安全、错误处理",
            },
        },
    },
)
class ReviewChangesAdapter(ToolAdapter):
    category = "system"
    timeout = 300

    def external_paths(self, workspace: Path, arguments: dict[str, Any]) -> list[str]:
        return []

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        ws = Path(workspace).resolve()
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(ws), "diff", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise ToolExecutionError(
                f"无法获取改动（工作区可能不是 git 仓库）: {detail[:300]}"
            )

        diff = stdout.decode("utf-8", errors="replace")
        if not diff.strip():
            return ToolResult(
                success=True,
                message="没有未提交的改动",
                content=(
                    "当前工作区没有未提交的改动（git diff HEAD 为空），无需审查。"
                    "新建的未跟踪文件不会出现在 diff 里，如需审查请先 git add。"
                ),
                data={"engine": "review_changes", "diff_chars": 0},
            )

        truncated = len(diff) > _MAX_DIFF_CHARS
        shown = diff[:_MAX_DIFF_CHARS]
        if truncated:
            shown += f"\n...(diff 已截断，原始 {len(diff)} 字符；建议分批提交后分别审查)"

        focus = str(arguments.get("focus") or "").strip()
        review = await _run_review(shown, focus)
        return ToolResult(
            success=True,
            message="代码审查完成",
            content=review,
            data={
                "diff_chars": len(diff),
                "truncated": truncated,
                "focus": focus or None,
            },
        )
