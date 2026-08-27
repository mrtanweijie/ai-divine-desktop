from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool


@register_tool(
    "move_file",
    "在 workspace 内移动或重命名文件/目录（自动创建目标父目录；目标已存在时需 overwrite=true）。"
    "只做移动，不更新其他文件里的引用；需要改引用时再用 edit_files。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "源路径（workspace 内相对或绝对）",
            },
            "new_path": {
                "type": "string",
                "description": "目标路径（workspace 内相对或绝对）",
            },
            "overwrite": {
                "type": "boolean",
                "description": "目标已存在时是否覆盖，默认 false",
                "default": False,
            },
        },
        "required": ["path", "new_path"],
    },
)
class MoveFileAdapter(ToolAdapter):
    category = "files"
    timeout = 20

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        del locale, progress_callback
        workspace = workspace.resolve()

        def _resolve(raw: str, field: str) -> Path:
            if not raw:
                raise ToolExecutionError(f"{field} 不能为空")
            p = Path(raw)
            if not p.is_absolute():
                p = workspace / p
            resolved = p.resolve()
            try:
                resolved.relative_to(workspace)
            except ValueError as exc:
                raise ToolExecutionError(f"{field} 必须位于工作区内: {raw}") from exc
            return resolved

        source = _resolve(str(arguments.get("path") or "").strip(), "path")
        dest = _resolve(
            str(arguments.get("new_path") or "").strip(), "new_path"
        )
        overwrite = bool(arguments.get("overwrite", False))
        if not source.exists():
            raise ToolExecutionError(f"源路径不存在: {source}")
        if source == dest:
            raise ToolExecutionError("源路径与目标路径相同")
        if source.is_dir() and (dest == source or source in dest.parents):
            raise ToolExecutionError("不能把目录移动到其自身的子目录中")
        if dest.exists():
            if not overwrite:
                raise ToolExecutionError(
                    f"目标已存在: {dest}，如要覆盖请传 overwrite=true"
                )
            if dest.is_dir() and not source.is_dir():
                raise ToolExecutionError("目标是目录而源是文件，拒绝覆盖")

        def _do_move() -> dict[str, Any]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, dest)
            return {"size": dest.stat().st_size}

        info = await asyncio.to_thread(_do_move)
        rel_from = source.relative_to(workspace).as_posix()
        rel_to = dest.relative_to(workspace).as_posix()
        return ToolResult(
            success=True,
            message=f"已移动 {rel_from} → {rel_to}",
            data={
                "from": rel_from,
                "to": rel_to,
                "is_dir": source.is_dir(),
                **info,
            },
        )
