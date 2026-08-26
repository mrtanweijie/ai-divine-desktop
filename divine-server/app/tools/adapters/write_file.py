from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult, resolve_external_path
from ..registry import register_tool

MAX_WRITE_FILE_CHARS = 1_000_000


@register_tool(
    "write_file",
    "创建或写入工作区内的文本文件（.rs/.py/.ts/.json/.md 等）。自动创建父目录；"
    "mode=append 追加内容；写入已存在文件需 overwrite=true；不要用 terminal heredoc 写文件。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "workspace 内相对路径或绝对路径，例如 src/lib.rs",
            },
            "content": {
                "type": "string",
                "description": "完整文件内容（UTF-8 文本）",
            },
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "description": "write 覆盖写入，append 追加内容",
            },
            "overwrite": {
                "type": "boolean",
                "description": "文件已存在时是否允许覆盖，默认 false",
            },
        },
        "required": ["path", "content"],
    },
)
class WriteFileAdapter(ToolAdapter):
    category = "files"
    timeout = 30
    allow_external_paths = True

    def external_paths(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> list[str]:
        external = resolve_external_path(
            workspace, arguments.get("path")
        )
        return [external] if external else []

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        raw_path = str(arguments.get("path") or "").strip()
        content = str(arguments.get("content") or "")
        mode = str(arguments.get("mode") or "write").strip()
        overwrite = bool(arguments.get("overwrite", False))
        if not raw_path:
            raise ToolExecutionError("path 不能为空")
        if len(content) > MAX_WRITE_FILE_CHARS:
            raise ToolExecutionError(
                f"文件内容超过 {MAX_WRITE_FILE_CHARS} 字符限制"
            )
        if mode not in {"write", "append"}:
            raise ToolExecutionError("mode 只支持 write 或 append")

        target = Path(raw_path)
        if not target.is_absolute():
            target = workspace / target
        target = target.resolve()
        if target.exists() and target.is_dir():
            raise ToolExecutionError("path 指向目录，不是文件")
        if mode == "write" and target.exists() and not overwrite:
            raise ToolExecutionError(
                f"文件已存在: {target}，如要覆盖请传 overwrite=true"
            )

        def _do_write() -> int:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open(
                "a" if mode == "append" else "w", encoding="utf-8"
            ) as handle:
                handle.write(content)
            return target.stat().st_size

        try:
            file_size = await asyncio.to_thread(_do_write)
        except OSError as exc:
            raise ToolExecutionError(f"文件写入失败: {exc}") from exc

        return ToolResult(
            success=True,
            message=(
                "文件已追加" if mode == "append" else "文件已写入"
            ),
            message_key=(
                "tool.fileAppended" if mode == "append" else "tool.fileWritten"
            ),
            message_params={},
            file_name=target.name,
            filepath=str(target),
            file_size=file_size,
            content=None,
            data={"mode": mode, "path": str(target)},
        )
