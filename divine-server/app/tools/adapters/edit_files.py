from __future__ import annotations

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


@register_tool(
    "edit_files",
    "批量修改或创建多个文本文件，必须一次调用完成所有改动，不要逐个文件修改。"
    "files 中每一项是一次 SEARCH/REPLACE：search 必须与文件现有内容完全一致"
    "（含缩进、空行和结尾换行），replace 是替换后的内容；"
    "search 传空字符串表示创建新文件。"
    "修改代码前先在正文中列出将要修改的文件和每个文件的改动点，再调用本工具。",
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
        self, workspace: Path, arguments: dict[str, Any]
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
        summary: list[dict[str, Any]] = []
        for index, (target, search, replace, count) in enumerate(edits, start=1):
            if target.is_dir():
                raise ToolExecutionError(f"第 {index} 个编辑项路径是目录: {target}")

            if not search:
                if target.exists():
                    raise ToolExecutionError(
                        f"要创建的文件已存在: {target}；修改已有文件必须提供 search"
                    )
                staged[target] = replace
                summary.append(
                    {
                        "path": _display_path(workspace, target),
                        "filepath": str(target),
                        "action": "created",
                        "replacements": 0,
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

            occurrences = text.count(search)
            if occurrences == 0:
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
                }
            )

        for target, text in staged.items():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise ToolExecutionError(f"写入文件失败: {target}: {exc}") from exc

        created = sum(1 for item in summary if item["action"] == "created")
        modified = len(summary) - created
        return ToolResult(
            success=True,
            message=f"已批量完成：新增 {created} 个文件，修改 {modified} 个文件",
            content=None,
            data={"files": summary},
        )
