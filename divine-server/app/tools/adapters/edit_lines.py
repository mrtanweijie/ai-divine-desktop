from __future__ import annotations

import asyncio
import difflib
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ..text_file_io import read_normalized, write_restored

MAX_LINE_EDITS = 50
_DIFF_CAP = 4000


def _parse_int(raw: Any, field: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ToolExecutionError(f"{field} 必须是整数")


def _strip_edge_newlines(content: str) -> str:
    """容忍模型在 content 首尾多打一个换行（常见失误），各剥一个。"""
    if content.startswith("\n"):
        content = content[1:]
    if content.endswith("\n"):
        content = content[:-1]
    return content


def _conflicts(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Conflict rules over inclusive original-numbering ranges.

    An empty range (start, start-1) is a zero-width insert before start:
    it only conflicts when it falls strictly inside another range, or when
    two inserts target the same position.
    """

    def is_empty(r: tuple[int, int]) -> bool:
        return r[1] < r[0]

    if is_empty(a) and is_empty(b):
        return a[0] == b[0]
    if is_empty(a):
        return b[0] <= a[0] <= b[1]
    if is_empty(b):
        return a[0] <= b[0] <= a[1]
    return a[0] <= b[1] and b[0] <= a[1]


def apply_line_edits(
    lines: list[str], edits: list[tuple[int, int, str]]
) -> tuple[list[str], list[tuple[tuple[int, int], tuple[int, int]]]]:
    """Apply range edits against ORIGINAL line numbers.

    Returns (new_lines, applied) where applied maps each edit's original
    (start, end) to its resulting (new_start, new_end) in the new numbering.
    """
    ordered = sorted(edits, key=lambda e: (e[0], e[1]), reverse=True)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            ra = (ordered[i][0], ordered[i][1])
            rb = (ordered[j][0], ordered[j][1])
            if _conflicts(ra, rb):
                raise ToolExecutionError(
                    f"行号范围冲突：{rb[0]}-{rb[1]} 与 {ra[0]}-{ra[1]}；"
                    "所有行号都按原始文件计算，请拆成互不冲突的区间"
                )
    # 自下而上收集片段（old 尾段 / 替换块），再倒序拼装即可保持原行号语义。
    plan: list[tuple[str, Any, tuple[int, int] | None]] = []
    cursor = len(lines)
    for start, end, replace in ordered:
        tail = lines[end:cursor]
        if tail:
            plan.append(("old", tail, None))
        rep = replace.split("\n") if replace else []
        plan.append(("rep", rep, (start, end)))
        cursor = start - 1
    if cursor > 0:
        plan.append(("old", lines[:cursor], None))

    new_lines: list[str] = []
    applied: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for kind, payload, original in reversed(plan):
        if kind == "old":
            new_lines.extend(payload)
        else:
            new_start = len(new_lines) + 1
            new_lines.extend(payload)
            applied.append((original, (new_start, len(new_lines))))
    return new_lines, applied


@register_tool(
    "edit_lines",
    "按行号范围精确编辑单个文件，作为 edit_files 的备选：SEARCH/REPLACE 难以构造时"
    "（大段重写、重复代码块）直接用 read_file 返回的行号编辑。"
    "edits 每项替换 [start_line, end_line]（含两端，行号按原始文件计）为 content；"
    "content 传空字符串删除该范围；end_line = start_line - 1 表示在 start_line 前插入。"
    "一次可提交多个不重叠的区间（内部自下而上应用，互不影响行号）；"
    "返回变更区间的 unified diff 供核对。创建新文件请用 write_file。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "workspace 内相对路径或绝对路径",
            },
            "edits": {
                "type": "array",
                "description": "编辑列表（≤50 项），所有行号均按编辑前的原始文件计算",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {
                            "type": "integer",
                            "description": "起始行（从 1 开始，read_file 输出的行号）",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": (
                                "结束行（含）。省略时等同 start_line；"
                                "传 start_line - 1 表示在该行前插入"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "替换后的完整内容；空字符串删除该范围；"
                                "首尾多余的换行会被自动剥离"
                            ),
                        },
                    },
                    "required": ["start_line", "content"],
                },
            },
        },
        "required": ["path", "edits"],
    },
)
class EditLinesAdapter(ToolAdapter):
    category = "files"
    timeout = 30

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        del locale, progress_callback
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ToolExecutionError("path 不能为空")
        target = Path(raw_path)
        if not target.is_absolute():
            target = workspace / target
        target = target.resolve()
        if target.is_dir():
            raise ToolExecutionError(f"path 指向目录: {target}")
        if not target.exists():
            raise ToolExecutionError(
                f"文件不存在: {target}（创建新文件请用 write_file）"
            )

        raw_edits = arguments.get("edits") or []
        if not isinstance(raw_edits, list) or not raw_edits:
            raise ToolExecutionError("edits 不能为空")
        if len(raw_edits) > MAX_LINE_EDITS:
            raise ToolExecutionError(f"一次最多提交 {MAX_LINE_EDITS} 个编辑项")

        def _do_work() -> ToolResult:
            text, traits = read_normalized(target)
            # 与 read_file 的行号保持一致：末尾换行不产生幻影空行，
            # 写回时按原样恢复。
            had_final_nl = text.endswith("\n")
            body = text[:-1] if had_final_nl else text
            lines = body.split("\n") if body else []
            total = len(lines)
            edits: list[tuple[int, int, str]] = []
            for index, item in enumerate(raw_edits, start=1):
                if not isinstance(item, dict):
                    raise ToolExecutionError(f"第 {index} 个编辑项必须是对象")
                start = _parse_int(item.get("start_line"), f"第 {index} 项 start_line")
                if start < 1:
                    raise ToolExecutionError(f"第 {index} 项 start_line 必须 ≥ 1")
                end_raw = item.get("end_line")
                if end_raw is None:
                    end = start
                else:
                    end = _parse_int(end_raw, f"第 {index} 项 end_line")
                    if end < start - 1:
                        raise ToolExecutionError(
                            f"第 {index} 项 end_line 只能 ≥ start_line - 1"
                            "（空区间表示插入）"
                        )
                if start > total + 1 or end > total:
                    raise ToolExecutionError(
                        f"第 {index} 项行号超出文件范围（共 {total} 行）："
                        f"{start}-{end}"
                    )
                replace = _strip_edge_newlines(str(item.get("content") or ""))
                edits.append((start, end, replace))

            new_lines, applied = apply_line_edits(lines, edits)
            new_text = (
                "\n".join(new_lines) + "\n"
                if new_lines and had_final_nl
                else "\n".join(new_lines)
            )
            rel = raw_path if target.is_relative_to(workspace.resolve()) else str(target)
            diff = "\n".join(
                difflib.unified_diff(
                    lines,
                    new_lines,
                    fromfile=rel,
                    tofile=rel,
                    lineterm="",
                )
            )
            write_restored(target, new_text, traits)
            applied_map = {
                original: new_span for original, new_span in applied
            }
            changed_ranges = []
            for start, end, _ in edits:
                new_span = applied_map[(start, end)]
                new_start, new_end = new_span
                changed_ranges.append(
                    {
                        "original": (
                            f"{start}-{end}" if end >= start else f"插入@{start}"
                        ),
                        "new": (
                            f"{new_start}-{new_end}"
                            if new_end >= new_start
                            else "(已删除)"
                        ),
                    }
                )
            return ToolResult(
                success=True,
                message=f"已完成 {len(edits)} 处行级编辑（{total} 行 → {len(new_lines)} 行）",
                content=(diff[:_DIFF_CAP] if diff else None),
                data={
                    "path": str(target),
                    "total_lines_before": total,
                    "total_lines_after": len(new_lines),
                    "applied": changed_ranges,
                    "diff_truncated": len(diff) > _DIFF_CAP,
                },
            )

        return await asyncio.to_thread(_do_work)
