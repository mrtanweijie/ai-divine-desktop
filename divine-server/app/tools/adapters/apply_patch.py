from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ..text_file_io import read_normalized, write_restored

_MAX_PATCH_CHARS = 200_000
_MAX_HUNK_OFFSET = 200
_WS_RUN = re.compile(r"\s+")


class Hunk:
    __slots__ = ("old_start", "old_count", "new_start", "new_count", "lines")

    def __init__(
        self,
        old_start: int,
        old_count: int,
        new_start: int,
        new_count: int,
        lines: list[str],
    ) -> None:
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines

    @property
    def removal(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith((" ", "-"))]

    @property
    def addition(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith((" ", "+"))]


class FilePatch:
    __slots__ = ("old_path", "new_path", "hunks")

    def __init__(self, old_path: str, new_path: str) -> None:
        self.old_path = old_path
        self.new_path = new_path
        self.hunks: list[Hunk] = []


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch_text: str) -> list[FilePatch]:
    """Parse a unified diff into per-file patch plans."""
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    hunk: Hunk | None = None
    for line in patch_text.split("\n"):
        if line.startswith("--- "):
            current = FilePatch(line[4:].strip(), "")
            patches.append(current)
            hunk = None
            continue
        if line.startswith("+++ ") and current is not None:
            current.new_path = line[4:].strip()
            continue
        match = _HUNK_RE.match(line)
        if match and current is not None:
            hunk = Hunk(
                int(match.group(1)),
                int(match.group(2)) if match.group(2) is not None else 1,
                int(match.group(3)),
                int(match.group(4)) if match.group(4) is not None else 1,
                [],
            )
            current.hunks.append(hunk)
            continue
        if hunk is not None:
            if line.startswith("\\"):  # "\ No newline at end of file"
                continue
            if line.startswith((" ", "-", "+")):
                hunk.lines.append(line)
                continue
            # 下一文件头或垃圾行：结束当前 hunk
            hunk = None
    return [p for p in patches if p.hunks or (p.old_path and p.new_path)]


def _strip_prefix(path: str) -> str:
    path = path.strip()
    if path == "/dev/null":
        return path
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path.removeprefix("./")


def _locate(
    lines: list[str], removal: list[str], expected_index: int
) -> tuple[int | None, bool]:
    """Find the removal block near expected_index.

    Returns (index, fuzzy). Exact match first (scanning outward up to
    _MAX_HUNK_OFFSET lines), then a whitespace-collapsed fallback.
    """
    n = len(lines)
    if not removal:
        return max(0, min(expected_index, n)), False

    def exact_at(index: int) -> bool:
        return (
            0 <= index
            and index + len(removal) <= n
            and lines[index : index + len(removal)] == removal
        )

    def fuzzy_at(index: int) -> bool:
        if index < 0 or index + len(removal) > n:
            return False
        for src, want in zip(lines[index : index + len(removal)], removal):
            if _WS_RUN.sub(" ", src).strip() != _WS_RUN.sub(" ", want).strip():
                return False
        return True

    for matcher, fuzzy in ((exact_at, False), (fuzzy_at, True)):
        for offset in range(_MAX_HUNK_OFFSET + 1):
            candidates = [expected_index - offset, expected_index + offset]
            if offset == 0:
                candidates = [expected_index]
            for candidate in candidates:
                if matcher(candidate):
                    return candidate, fuzzy
    return None, False


def apply_file_patch(
    text: str, patch: FilePatch
) -> tuple[str, list[tuple[int, bool]], str]:
    """Apply hunks to normalized text. Returns (new_text, applied, error).

    All-or-nothing per file: on any hunk failure the original text is
    returned with an error message.
    """
    had_final_nl = text.endswith("\n")
    body = text[:-1] if had_final_nl else text
    lines = body.split("\n") if body else []
    applied: list[tuple[int, bool]] = []
    shift = 0
    for hunk in patch.hunks:
        removal = hunk.removal
        addition = hunk.addition
        expected = hunk.old_start - 1 + shift
        index, fuzzy = _locate(lines, removal, expected)
        if index is None:
            return (
                text,
                applied,
                f"hunk @{hunk.old_start} 上下文不匹配（已尝试 ±{_MAX_HUNK_OFFSET} 行与空白容错）；"
                "请基于最新文件内容重新生成 patch",
            )
        lines[index : index + len(removal)] = addition
        applied.append((hunk.old_start, fuzzy))
        shift += len(addition) - len(removal)
    new_body = "\n".join(lines)
    if had_final_nl and new_body:
        new_body += "\n"
    return new_body, applied, ""


@register_tool(
    "apply_patch",
    "把 unified diff 补丁应用到工作区文件（支持一个补丁改多个文件、新建 /dev/null 来源的文件）。"
    "hunk 按上下文定位：允许行号漂移 ±200 行与空白差异容错，单个文件内任一 hunk 失败则该文件"
    "整体不写入。适合模型以标准 diff 格式一次性描述多处改动；简单修改优先用 edit_files/edit_lines。",
    {
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": (
                    "标准 unified diff 文本，可含多个文件的 ---/+++/@@ 块；"
                    "新建文件用 --- /dev/null"
                ),
            },
        },
        "required": ["patch"],
    },
)
class ApplyPatchAdapter(ToolAdapter):
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
        workspace = workspace.resolve()
        patch_text = str(arguments.get("patch") or "")
        if not patch_text.strip():
            raise ToolExecutionError("patch 不能为空")
        if len(patch_text) > _MAX_PATCH_CHARS:
            raise ToolExecutionError(f"补丁超过 {_MAX_PATCH_CHARS} 字符限制")
        patches = parse_patch(patch_text)
        if not patches:
            raise ToolExecutionError(
                "未解析出有效的 diff 内容；需要 ---/+++ 与 @@ 头的标准 unified diff"
            )

        def _resolve(path: str) -> Path:
            p = Path(path)
            if not p.is_absolute():
                p = workspace / p
            resolved = p.resolve()
            try:
                resolved.relative_to(workspace)
            except ValueError as exc:
                raise ToolExecutionError(f"补丁路径越界: {path}") from exc
            return resolved

        def _do_work() -> ToolResult:
            files: list[dict[str, Any]] = []
            errors: list[str] = []
            for patch in patches:
                old_raw = _strip_prefix(patch.old_path or "")
                new_raw = _strip_prefix(patch.new_path or old_raw)
                is_creation = old_raw == "/dev/null"
                target = _resolve(new_raw)
                if is_creation:
                    if target.exists():
                        errors.append(f"{target}: 新建文件已存在")
                        continue
                    creation_lines: list[str] = []
                    for hunk in patch.hunks:
                        creation_lines.extend(hunk.addition)
                    write_restored(
                        target, "\n".join(creation_lines) + "\n", None
                    )
                    files.append(
                        {
                            "path": str(target.relative_to(workspace)),
                            "action": "created",
                            "hunks": len(patch.hunks),
                        }
                    )
                    continue
                if not target.exists():
                    errors.append(f"{target}: 文件不存在")
                    continue
                text, traits = read_normalized(target)
                new_text, applied, error = apply_file_patch(text, patch)
                if error:
                    errors.append(f"{target}: {error}")
                    continue
                write_restored(target, new_text, traits)
                fuzzy_used = any(fuzzy for _, fuzzy in applied)
                files.append(
                    {
                        "path": str(target.relative_to(workspace)),
                        "action": "modified",
                        "hunks": len(applied),
                        "fuzzy": fuzzy_used,
                    }
                )
            success = bool(files) and not errors
            message_parts = [f"已应用 {len(files)} 个文件"]
            if errors:
                message_parts.append(f"{len(errors)} 个失败")
            return ToolResult(
                success=success,
                message="；".join(message_parts),
                content="\n".join(
                    [
                        f"{item['action']}: {item['path']} ({item['hunks']} hunks)"
                        for item in files
                    ]
                    + [f"ERROR: {item}" for item in errors]
                )
                or None,
                data={
                    "files": files,
                    "errors": errors,
                },
            )

        return await asyncio.to_thread(_do_work)
