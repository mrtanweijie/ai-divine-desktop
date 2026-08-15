"""Tool execution, output annotation, and timeout handling."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .. import db
from ..tools.base import ToolExecutionError

logger = logging.getLogger("divine.agent.tool_runtime")

def _summarize_arguments(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 80:
            parts.append(f"{key}={len(value)}chars")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)[:500]

_STATIC_TOOL_SUCCESS_KEYS = {
    "notes": "tool.notesCreated",
    "word_document": "tool.wordCreated",
    "presentation": "tool.presentationCreated",
    "spreadsheet": "tool.spreadsheetCreated",
    "pdf_generate": "tool.pdfGenerated",
    "pdf_render": "tool.pdfRendered",
    "read_image": "tool.imageAnalyzed",
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
) -> dict[str, Any]:
    """Run one adapter call with timeout, logging, and persistent tool runs."""
    run = db.add_tool_run(session_id, name, "start", arguments)
    started = time.monotonic()
    logger.info("tool start session=%s name=%s", session_id, name)
    logger.info(
        "tool args session=%s name=%s args=[%s]",
        session_id,
        name,
        _summarize_arguments(arguments),
    )
    try:
        result = await asyncio.wait_for(
            adapter.run(
                workspace,
                arguments,
                locale=locale or "zh-CN",
                progress_callback=progress_callback,
            ),
            timeout=adapter.timeout,
        )
        output = result.as_dict()
        output = _annotate_tool_output(name, output, arguments)
        db.update_tool_run(run["id"], "done", output)
        logger.info(
            "tool done session=%s name=%s duration=%.2fs success=%s",
            session_id,
            name,
            time.monotonic() - started,
            output.get("success"),
        )
        return output
    except asyncio.TimeoutError:
        output = {
            "success": False,
            "message": f"工具执行超时（{adapter.timeout}s）",
            "messageKey": "tool.toolTimeout",
            "messageParams": {"timeout": adapter.timeout},
        }
        db.update_tool_run(run["id"], "error", output)
        logger.warning(
            "tool timeout session=%s name=%s duration=%.2fs timeout=%s",
            session_id,
            name,
            time.monotonic() - started,
            adapter.timeout,
        )
        return output
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
        db.update_tool_run(run["id"], "error", output)
        logger.warning(
            "tool error session=%s name=%s duration=%.2fs error=%s",
            session_id,
            name,
            time.monotonic() - started,
            exc,
        )
        return output
