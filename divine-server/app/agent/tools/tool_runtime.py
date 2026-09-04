"""Tool execution, output annotation, and timeout handling."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ... import db
from ...tools.base import ToolExecutionError

logger = logging.getLogger("divine.agent.tool_runtime")

# 超时自动重试白名单：幂等只读的网络类工具。超时多为瞬时抖动，
# 自动重试一次的成本远低于"把错误丢回模型、指望它自觉重试"。
# 写操作/终端类绝不自动重试——副作用不可撤销。
_RETRYABLE_TOOLS = {"web_search", "web_fetch", "web_fetch_batch", "rag_search"}
_MAX_TIMEOUT_ATTEMPTS = 2

def _summarize_arguments(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 80:
            parts.append(f"{key}={len(value)}chars")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)[:500]

_STORAGE_STRING_KEEP = 200
_STORAGE_STRING_LIMIT = 400

def _compact_for_storage(value: Any) -> Any:
    """Deep-truncate long strings before persisting tool runs to SQLite."""
    if isinstance(value, str):
        if len(value) > _STORAGE_STRING_LIMIT:
            return (
                value[:_STORAGE_STRING_KEEP]
                + f"...(truncated, total {len(value)} chars)"
            )
        return value
    if isinstance(value, dict):
        return {k: _compact_for_storage(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact_for_storage(item) for item in value]
    return value

_STATIC_TOOL_SUCCESS_KEYS = {
    "notes": "tool.notesCreated",
    "word_document": "tool.wordCreated",
    "presentation": "tool.presentationCreated",
    "spreadsheet": "tool.spreadsheetCreated",
    "pdf_generate": "tool.pdfGenerated",
    "pdf_render": "tool.pdfRendered",
    "read_image": "tool.imageAnalyzed",
    "image_generate": "tool.imageGenerated",
    "calculator": "tool.calculationDone",
    "image_resize": "tool.imageResized",
    "mermaid_export": "tool.mermaidExported",
    "draw_svg": "tool.svgCreated",
    "edit_svg": "tool.svgUpdated",
    "describe_svg": "tool.svgDescribed",
    "svg_to_png": "tool.svgExportedPng",
    "ux_html": "tool.uxHtmlCreated",
    "generate_chart": "tool.chartGenerated",
    "terminal": "tool.commandDone",
    "rag_index": "tool.ragIndexed",
}

def _tool_success_message(
    name: str,
    output: dict[str, Any],
    arguments: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    key = _STATIC_TOOL_SUCCESS_KEYS.get(name)
    if name == "read_file":
        data = output.get("data") or {}
        params: dict[str, Any] = {
            "name": output.get("file_name") or "",
            "start": data.get("line_start"),
            "end": data.get("line_end"),
            "total": data.get("total_lines"),
        }
        has_range = (
            arguments.get("start_line") is not None
            or arguments.get("end_line") is not None
        )
        return (
            "tool.fileReadRange" if has_range else "tool.fileRead",
            params,
        )
    if name == "directory_tree":
        try:
            tree = json.loads(output.get("content") or "{}").get("tree") or []
        except (TypeError, json.JSONDecodeError):
            tree = []
        return "tool.directoryScanned", {"count": len(tree)}
    if name == "sqlite_query":
        try:
            rows = json.loads(output.get("content") or "{}").get("rows") or []
        except (TypeError, json.JSONDecodeError):
            rows = []
        return "tool.queryDoneRows", {"count": len(rows)}
    if name == "search_files":
        try:
            files = json.loads(output.get("content") or "[]")
        except (TypeError, json.JSONDecodeError):
            files = []
        return "tool.filesFound", {"count": len(files)}
    if name == "rag_search":
        try:
            results = json.loads(output.get("content") or "[]")
        except (TypeError, json.JSONDecodeError):
            results = []
        return (
            "tool.ragSearchResults",
            {"count": len(results)},
        )
    if name == "rag_index":
        try:
            indexed = json.loads(output.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            indexed = {}
        return (
            "tool.ragIndexed",
            {
                "files": indexed.get("files", 0),
                "chunks": indexed.get("chunks", 0),
            },
        )
    if name == "web_fetch":
        return "tool.webFetched", {"url": output.get("url") or ""}
    if name == "web_fetch_batch":
        results = (output.get("data") or {}).get("results") or []
        success = sum(
            1 for item in results if isinstance(item, dict) and item.get("success")
        )
        return (
            "tool.webFetchedBatch",
            {"success": success, "total": len(results)},
        )
    if name == "svg_to_png_batch":
        results = (output.get("data") or {}).get("results") or []
        success = sum(
            1 for item in results if isinstance(item, dict) and item.get("success")
        )
        return "tool.svgExportedPngBatch", {"count": success}
    if name == "pdf_split_merge":
        action = str(arguments.get("action") or "").lower()
        if action == "merge":
            return "tool.pdfMerged", {}
        if arguments.get("pages"):
            return "tool.pdfPagesExtracted", {}
        return "tool.pdfSplit", {}
    if name == "clipboard":
        action = str(arguments.get("action") or "read").lower()
        return {
            "write": "tool.clipboardWritten",
            "clear": "tool.clipboardCleared",
            "read": "tool.clipboardRead",
        }.get(action, "tool.clipboardRead"), {}
    if name == "edit_files":
        files = (output.get("data") or {}).get("files") or []
        created = sum(
            1 for item in files if isinstance(item, dict) and item.get("action") == "created"
        )
        return (
            "tool.filesEdited",
            {"created": created, "modified": len(files) - created},
        )
    if name == "write_file":
        mode = str(arguments.get("mode") or "write").lower()
        return (
            "tool.fileAppended" if mode == "append" else "tool.fileWritten",
            {},
        )
    if key:
        return key, {}
    return None

def _annotate_tool_output(
    name: str,
    output: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if output.get("messageKey"):
        return output
    if not output.get("success"):
        return output
    localized = _tool_success_message(name, output, arguments)
    if not localized:
        return output
    annotated = dict(output)
    annotated["messageKey"], annotated["messageParams"] = localized
    return annotated

async def _execute_tool(
    session_id: str,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
    workspace: Any,
    locale: str | None = None,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    run_meta: dict[str, Any] | None = None,
    turn: int | None = None,
    on_retry: Callable[[int], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Run one adapter call with timeout, logging, and persistent tool runs.

    ``run_meta`` 是调用方持有的旁路字典：这里回填 run_id / started_at /
    duration_ms，供 tool SSE 事件携带。刻意不走返回值——output 会进入
    tool_content 喂给模型，运行时元数据不应混入模型上下文。
    ``turn``（模型调用轮次）与 ``duration_ms`` 一并落库，供刷新后恢复
    执行轨迹（TracePanel）使用。
    ``on_retry(attempt)``：幂等只读工具超时自动重试时回调（发 SSE 提示）。
    重试仅针对 TimeoutError——它是明确的瞬时故障；其余错误不重试，
    避免放大失败延迟。重试对落库透明：一次调用仍是一条 tool_run，
    duration 为所有 attempt 的总耗时。
    """

    def _record(duration_ms_value: int) -> None:
        if run_meta is None:
            return
        run_meta["run_id"] = run["id"]
        run_meta["started_at"] = run.get("started_at")
        run_meta["duration_ms"] = duration_ms_value

    run = await asyncio.to_thread(
        db.add_tool_run,
        session_id,
        name,
        "start",
        _compact_for_storage(arguments),
        None,
        turn,
    )
    started = time.monotonic()
    logger.info("tool start session=%s name=%s", session_id, name)
    logger.info(
        "tool args session=%s name=%s args=[%s]",
        session_id,
        name,
        _summarize_arguments(arguments),
    )
    effective_timeout = (
        adapter.effective_timeout(arguments)
        if hasattr(adapter, "effective_timeout")
        else adapter.timeout
    )
    result = None
    attempt = 0
    while True:
        attempt += 1
        try:
            result = await asyncio.wait_for(
                adapter.run(
                    workspace,
                    arguments,
                    locale=locale or "zh-CN",
                    progress_callback=progress_callback,
                ),
                timeout=effective_timeout,
            )
        except ToolExecutionError as exc:
            output = {
                "success": False,
                "message": str(exc),
                "messageKey": exc.message_key,
                "messageParams": exc.message_params or {},
            }
            if not output["messageKey"]:
                output.pop("messageKey")
            if not output["messageParams"]:
                output.pop("messageParams")
            error_duration_ms = round((time.monotonic() - started) * 1000)
            await asyncio.to_thread(
                db.update_tool_run, run["id"], "error", output, error_duration_ms
            )
            _record(error_duration_ms)
            logger.warning(
                "tool error session=%s name=%s duration=%.2fs error=%s",
                session_id,
                name,
                time.monotonic() - started,
                exc,
            )
            return output
        except asyncio.TimeoutError:
            if (
                name in _RETRYABLE_TOOLS
                and attempt < _MAX_TIMEOUT_ATTEMPTS
            ):
                logger.warning(
                    "tool timeout, retrying session=%s name=%s "
                    "attempt=%d timeout=%ss",
                    session_id,
                    name,
                    attempt,
                    effective_timeout,
                )
                if on_retry is not None:
                    await on_retry(attempt)
                continue
            output = {
                "success": False,
                "message": f"工具执行超时（{effective_timeout}s）",
                "messageKey": "tool.toolTimeout",
                "messageParams": {"timeout": effective_timeout},
            }
            timeout_duration_ms = round((time.monotonic() - started) * 1000)
            await asyncio.to_thread(
                db.update_tool_run,
                run["id"],
                "error",
                output,
                timeout_duration_ms,
            )
            _record(timeout_duration_ms)
            logger.warning(
                "tool timeout session=%s name=%s duration=%.2fs "
                "timeout=%s attempts=%d",
                session_id,
                name,
                time.monotonic() - started,
                effective_timeout,
                attempt,
            )
            return output
        output = result.as_dict()
        output = _annotate_tool_output(name, output, arguments)
        duration_ms = round((time.monotonic() - started) * 1000)
        await asyncio.to_thread(
            db.update_tool_run,
            run["id"],
            "done",
            _compact_for_storage(output),
            duration_ms,
        )
        _record(duration_ms)
        logger.info(
            "tool done session=%s name=%s duration=%.2fs success=%s "
            "attempts=%d",
            session_id,
            name,
            time.monotonic() - started,
            output.get("success"),
            attempt,
        )
        return output
