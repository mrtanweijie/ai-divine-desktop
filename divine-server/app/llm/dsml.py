"""Incremental DSML tool-call parser for streaming model output."""

from __future__ import annotations

import html
import json
import re
from typing import Any

_DSML_TOKEN_RE = re.compile(r"[｜|]{1,}\s*DSML\s*[｜|]{1,}", re.IGNORECASE)

_DSML_START_RE = re.compile(
    r"<(?:\s*[｜|]{1,}\s*DSML\s*[｜|]{1,}\s*)?(?:tool_calls|function_calls)\b.*?>"
    r"|<(?:\s*[｜|]{1,}\s*DSML\s*[｜|]{1,}\s*)?invoke\b",
    re.IGNORECASE,
)

_INVOKE_RE = re.compile(
    r"(?is)<invoke\s+name\s*=\s*([\"'])(.*?)\1\s*>(.*?)</invoke\s*>"
)

_PARAM_RE = re.compile(
    r"(?is)<parameter\s+name\s*=\s*([\"'])(.*?)\1"
    r"(?:\s+string\s*=\s*[\"'](?:true|false)[\"'])?\s*>"
    r"(.*?)</parameter\s*>"
)

_CDATA_RE = re.compile(r"(?is)<!\[CDATA\[(.*?)\]\]>")

_MARKDOWN_LINK_RE = re.compile(r"(?is)^\[([^\]]+)\]\((https?://[^)]+)\)$")

def _strip_dsml_tokens(text: str) -> str:
    return _DSML_TOKEN_RE.sub("", text)

def _clean_dsml_value(value: str) -> str:
    value = value.strip()
    value = _CDATA_RE.sub(lambda match: match.group(1), value).strip()
    link = _MARKDOWN_LINK_RE.fullmatch(value)
    if link:
        return link.group(2)
    return value

def _parse_dsml(raw: str, seq: int) -> list[dict[str, str]]:
    text = _strip_dsml_tokens(raw)
    calls = []
    for index, match in enumerate(_INVOKE_RE.finditer(text)):
        name = html.unescape(match.group(2)).strip()
        body = match.group(3)
        arguments: dict[str, Any] = {}
        for _, param_name, param_value in _PARAM_RE.findall(body):
            arguments[html.unescape(param_name).strip()] = _clean_dsml_value(
                param_value
            )
        calls.append(
            {
                "index": index,
                "id": f"dsml_{seq + index}",
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            }
        )
    return calls

def _find_dsml_start(text: str, start: int) -> int | None:
    match = _DSML_START_RE.search(text, start)
    return match.start() if match else None

def _find_dsml_end(text: str, block_start: int) -> int | None:
    segment = text[block_start:]
    wrapper = re.match(
        r"<(?:\s*[｜|]{1,}\s*DSML\s*[｜|]{1,}\s*)?(?:tool_calls|function_calls)\b",
        segment,
        re.IGNORECASE,
    )
    pattern = (
        r"</(?:\s*[｜|]{1,}\s*DSML\s*[｜|]{1,}\s*)?(?:tool_calls|function_calls)\s*>"
        if wrapper
        else r"</(?:\s*[｜|]{1,}\s*DSML\s*[｜|]{1,}\s*)?invoke\s*>"
    )
    match = re.search(pattern, segment, re.IGNORECASE)
    return block_start + match.end() if match else None

class DsmlStreamProcessor:
    def __init__(self) -> None:
        self.text = ""
        self.cursor = 0
        self.in_block = False
        self.block_start: int | None = None
        self._call_seq = 0

    def push(self, chunk: str) -> list[dict[str, Any]]:
        self.text += chunk
        return self._scan()

    def flush(self) -> list[dict[str, Any]]:
        if self.in_block:
            self.in_block = False
            self.block_start = None
            self.cursor = len(self.text)
            return []
        events = []
        tail = self.text[self.cursor:]
        if tail:
            events.append({"type": "message", "content": tail})
            self.cursor = len(self.text)
        return events

    def _scan(self) -> list[dict[str, Any]]:
        events = []
        while True:
            if not self.in_block:
                start = _find_dsml_start(self.text, self.cursor)
                if start is None:
                    break
                if start > self.cursor:
                    prefix = self.text[self.cursor:start].rstrip()
                    if not prefix:
                        self.cursor = start
                        continue
                    events.append(
                        {"type": "message", "content": prefix}
                    )
                    self.cursor = start
                self.in_block = True
                self.block_start = start
            assert self.block_start is not None
            end = _find_dsml_end(self.text, self.block_start)
            if end is None:
                break
            raw = self.text[self.block_start:end]
            calls = _parse_dsml(raw, self._call_seq)
            self._call_seq += len(calls)
            for call in calls:
                events.append({"type": "tool_call", **call})
            self.cursor = end
            self.in_block = False
            self.block_start = None
        return events
