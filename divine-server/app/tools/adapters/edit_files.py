from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from ..base import (
    ToolAdapter,
    ToolExecutionError,
    ToolResult,
    resolve_external_path,
)
from ..registry import register_tool

MAX_EDIT_FILES = 50
MAX_EDIT_TEXT_CHARS = 1_000_000
MAX_DIFF_CHARS = 120_000

_WS_RUN = re.compile(r"\s+")


def _normalize_count(raw: Any) -> int:
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ToolExecutionError("count 必须是整数")
    if raw == 0 or raw < -1:
        raise ToolExecutionError("count 只支持正整数或 -1（替换全部）")
    return raw


def _display_path(workspace: Path, target: Path) -> str:
    try:
        return str(target.relative_to(workspace))
    except ValueError:
        return str(target)


def _collapse_spans(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Collapse every whitespace run to one space; return (collapsed, spans)
    where spans[i] is the (start, end) slice of the original text that maps to
    collapsed character i."""
    collapsed: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            collapsed.append(" ")
            spans.append((i, j))
            i = j
        else:
            collapsed.append(text[i])
            spans.append((i, i + 1))
            i += 1
    return "".join(collapsed), spans


def _fuzzy_candidates(text: str, search: str) -> list[tuple[int, int]]:
    """Find original-text spans whose whitespace-collapsed form equals the
    whitespace-collapsed search. Returns [] when nothing matches."""
    collapsed_text, spans = _collapse_spans(text)
    collapsed_search = _WS_RUN.sub(" ", search).strip()
    if not collapsed_search:
        return []
    candidates: list[tuple[int, int]] = []
    start = 0
    while True:
        pos = collapsed_text.find(collapsed_search, start)
        if pos < 0:
            break
        span_start = spans[pos][0]
        span_end = spans[pos + len(collapsed_search) - 1][1]
        candidates.append((span_start, span_end))
        start = pos + 1
    return candidates


def _unified_diff(rel_path: str, old: str, new: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=rel_path,
        tofile=rel_path,
        lineterm="",
    )
    return "\n".join(diff)


def _cap_diff(diff: str) -> tuple[str, bool]:
    if len(diff) <= MAX_DIFF_CHARS:
        return diff, False
    return diff[:MAX_DIFF_CHARS] + "\n...(diff 已截断)", True


@register_tool(
    "edit_files",
    "批量修改或创建多个文本文件，一次调用完成所有改动。files 每项是一次 SEARCH/REPLACE："
    "search 必须与文件现有内容完全一致（含缩进、空行和结尾换行），空字符串表示创建新文件，"
    "replace 是替换后的内容。SEARCH 完全一致时精确替换；仅存在空白差异（缩进/空行不一致）时"
    "若唯一匹配会做模糊替换并标注。返回每个文件的 unified diff 供核对。"
    "修改前先在正文列出要修改的文件和改动点。",
    {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "workspace 内相对路径或绝对路径，例如 src/app.py",
                        },
                        "search": {
                            "type": "string",
                            "description": (
                                "要匹配的现有文本，必须完全一致（含缩进、空行和结尾换行）；"
                                "空字符串表示创建新文件"
                            ),
                        },
                        "replace": {
                            "type": "string",
                            "description": "替换后的文本；创建新文件时作为完整文件内容",
                        },
                        "count": {
                            "type": "integer",
                            "description": "替换次数，默认 1 只替换第一处；传 -1 替换全部",
                            "default": 1,
                        },
                    },
                    "required": ["path", "search", "replace"],
                },
                "description": "要执行的编辑列表",
            }
        },
        "required": ["files"],
    },
)
class EditFilesAdapter(ToolAdapter):
    category = "files"
    timeout = 60
    allow_external_paths = True

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        paths: list[str] = []
        for item in arguments.get("files") or []:
            if isinstance(item, dict):
                external = resolve_external_path(workspace, item.get("path"))
                if external:
                    paths.append(external)
        return paths

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        workspace = workspace.resolve()
        raw_files = arguments.get("files") or []
        if not isinstance(raw_files, list) or not raw_files:
            raise ToolExecutionError("files 不能为空，必须传入要修改的文件列表")
        if len(raw_files) > MAX_EDIT_FILES:
            raise ToolExecutionError(f"一次最多修改 {MAX_EDIT_FILES} 个文件")

        edits: list[tuple[Path, str, str, int]] = []
        for index, item in enumerate(raw_files, start=1):
            if not isinstance(item, dict):
                raise ToolExecutionError(f"第 {index} 个编辑项必须是对象")
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                raise ToolExecutionError(f"第 {index} 个编辑项缺少 path")
            search = str(item.get("search") or "")
            replace = str(item.get("replace") or "")
            if len(search) > MAX_EDIT_TEXT_CHARS or len(replace) > MAX_EDIT_TEXT_CHARS:
                raise ToolExecutionError(
                    f"第 {index} 个编辑项内容超过 {MAX_EDIT_TEXT_CHARS} 字符限制"
                )
            target = Path(raw_path)
            if not target.is_absolute():
                target = workspace / target
            edits.append((target.resolve(), search, replace, _normalize_count(item.get("count"))))

        staged: dict[Path, str] = {}
        originals: dict[Path, str] = {}
        summary: list[dict[str, Any]] = []
        fuzzy_used = False
        for index, (target, search, replace, count) in enumerate(edits, start=1):
            if target.is_dir():
                raise ToolExecutionError(f"第 {index} 个编辑项路径是目录: {target}")

            if not search:
                if target.exists():
                    raise ToolExecutionError(
                        f"要创建的文件已存在: {target}；修改已有文件必须提供 search"
                    )
                staged[target] = replace
                originals[target] = ""
                summary.append(
                    {
                        "path": _display_path(workspace, target),
                        "filepath": str(target),
                        "action": "created",
                        "replacements": 0,
                        "fuzzy": False,
                    }
                )
                continue

            if not target.exists():
                raise ToolExecutionError(f"文件不存在: {target}")
            text = staged.get(target)
            if text is None:
                try:
                    text = target.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise ToolExecutionError(
                        f"文件不是 UTF-8 文本，无法按文本替换: {target}"
                    ) from exc
                except OSError as exc:
                    raise ToolExecutionError(f"读取文件失败: {target}: {exc}") from exc
                originals[target] = text

            occurrences = text.count(search)
            used_fuzzy = False
            if occurrences == 0:
                candidates = _fuzzy_candidates(text, search)
                if len(candidates) == 1 and count in (1, -1):
                    span_start, span_end = candidates[0]
                    new_text = text[:span_start] + replace + text[span_end:]
                    staged[target] = new_text
                    summary.append(
                        {
                            "path": _display_path(workspace, target),
                            "filepath": str(target),
                            "action": "modified",
                            "replacements": 1,
                            "fuzzy": True,
                        }
                    )
                    fuzzy_used = True
                    continue
                if len(candidates) > 1:
                    sample = [
                        f"第 {s} 行附近" for s, _ in candidates[:3]
                    ]
                    raise ToolExecutionError(
                        f"第 {index} 个编辑项 SEARCH 在 {target} 中未精确匹配，"
                        f"模糊匹配到 {len(candidates)} 处（{'、'.join(sample)}），"
                        "请提供更精确的 SEARCH（包含独特上下文行）"
                    )
                raise ToolExecutionError(
                    f"第 {index} 个编辑项 SEARCH 未在 {target} 中找到。"
                    "SEARCH 必须与文件现有内容完全一致（含缩进、空行和结尾换行），"
                    "可先调用 read_file 查看文件内容"
                )
            if count != -1 and occurrences < count:
                raise ToolExecutionError(
                    f"第 {index} 个编辑项在 {target} 中只出现 {occurrences} 次，"
                    f"少于请求的 {count} 次"
                )
            if count == -1:
                new_text = text.replace(search, replace)
                actual = occurrences
            else:
                new_text = text.replace(search, replace, count)
                actual = count
            staged[target] = new_text
            summary.append(
                {
                    "path": _display_path(workspace, target),
                    "filepath": str(target),
                    "action": "modified",
                    "replacements": actual,
                    "fuzzy": False,
                }
            )

        for target, text in staged.items():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise ToolExecutionError(f"写入文件失败: {target}: {exc}") from exc

        # Build per-file unified diffs (after writing, from staged originals).
        diffs: list[str] = []
        diff_truncated = False
        for target, text in staged.items():
            rel = _display_path(workspace, target)
            old = originals.get(target, "")
            diff = _unified_diff(rel, old, text)
            if diff:
                capped, truncated = _cap_diff(diff)
                diffs.append(capped)
                diff_truncated = diff_truncated or truncated
            for item in summary:
                if item.get("filepath") == str(target):
                    item["diff"] = diff or None
                    break
        combined_diff = "\n".join(diffs) if diffs else None
        if combined_diff is not None:
            combined_diff, diff_truncated = _cap_diff(combined_diff)

        created = sum(1 for item in summary if item["action"] == "created")
        modified = len(summary) - created
        return ToolResult(
            success=True,
            message=(
                f"已批量完成：新增 {created} 个文件，修改 {modified} 个文件"
                + ("（部分为模糊匹配替换）" if fuzzy_used else "")
            ),
            message_key="tool.filesEdited",
            message_params={"created": created, "modified": modified},
            content=None,
            data={
                "files": summary,
                "diff": combined_diff,
                "diff_truncated": diff_truncated,
                "fuzzy_used": fuzzy_used,
            },
        )
