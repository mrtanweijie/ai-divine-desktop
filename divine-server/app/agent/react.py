"""ReAct text-mode tool calling: trace parser, SSE stream filter, middleware.

ReAct (Reasoning + Acting) lets models that do not support native function
calling drive the tool system with plain text: the model emits

    Thought: <reasoning>
    Action: <tool name>
    Action Input: <JSON object>

until it is done, then emits

    Final Answer: <answer>

Execution bridge: :class:`ReActParseMiddleware` strips the tools from the
model binding (so the model produces text), parses the finished trace, and
rewrites the AIMessage with standard ``tool_calls`` — from the LangGraph
graph's point of view nothing changed, so the tools node, approval
middleware, todo sync, limits, checkpointer and persistence all keep
working unchanged.

Streaming UX: :class:`ReActStreamProcessor` classifies the raw token stream
incrementally (tolerant of arbitrary chunk splits): ``Thought`` content is
forwarded as ``think`` events, the ``Action``/``Action Input``/``Observation``
scaffolding is suppressed (the real tool card is emitted later by the
adapter), and everything else is forwarded as ``message`` events.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware, ModelResponse
from langchain_core.messages import AIMessage

from .schema import _content_text

logger = logging.getLogger("divine.agent.react")

# --- limits ---------------------------------------------------------------

REACT_MAX_ACTION_INPUT_LEN = 8192
REACT_MAX_THOUGHT_LEN = 2000

# --- prompt ---------------------------------------------------------------

REACT_FORMAT_PROMPT = """【ReAct 文本工具调用模式】
当前模型不启用原生函数调用，需要调用工具时按以下格式逐行输出（关键词固定为英文）：
Thought: 推理
Action: 工具名
Action Input: {"参数": 值}
工具执行结果会以 Observation 形式返回给你；根据结果继续 Thought → Action，直到完成；
完成时以 “Final Answer: ” 开头输出最终回答。
规则：
- Action 只能使用系统提供的工具名，Action Input 必须是合法 JSON 且与工具参数定义一致；
  参数不确定时先用 read_file / search_files 了解情况，不要编造；
- 每轮只输出一个 Action；不要输出 XML/伪代码形式的调用；不要杜撰工具；
- 正文中的普通解释文字可以正常输出，但不要与 Action 格式混淆。"""

# --- trace model ----------------------------------------------------------

_KEYWORD_LINE_RE = re.compile(
    r"^\s*(Thought|Action Input|Action|Observation|Final Answer)\s*[:：]\s*(.*)$",
    re.IGNORECASE,
)

# Longer keywords first so "Action Input" wins over "Action".
_KEYWORDS = ("thought", "action input", "action", "observation", "final answer")


@dataclass
class ReActAction:
    name: str
    arguments: dict[str, Any]
    raw_input: str = ""
    error: str | None = None


@dataclass
class ReActTrace:
    thoughts: list[str] = field(default_factory=list)
    actions: list[ReActAction] = field(default_factory=list)
    final_answer: str | None = None
    prose: list[str] = field(default_factory=list)


def _extract_json(raw: str) -> tuple[dict[str, Any], str | None]:
    """Parse a JSON object from raw text, tolerating trailing prose.

    Falls back to brace-pair extraction when the whole string is not valid
    JSON. Returns ``({}, error)`` on failure so callers can decide how to
    surface the problem.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}, None
    if len(raw) > REACT_MAX_ACTION_INPUT_LEN:
        return {}, "Action Input 超过长度上限"
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value, None
        return {}, "Action Input 必须是 JSON 对象"
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start == -1:
        return {}, "Action Input 缺少 JSON 对象"
    depth = 0
    in_str = False
    esc = False
    end = -1
    limit = min(len(raw), start + REACT_MAX_ACTION_INPUT_LEN * 2)
    for index in range(start, limit):
        ch = raw[index]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end == -1:
        return {}, "Action Input JSON 不完整"
    try:
        value = json.loads(raw[start : end + 1])
        if isinstance(value, dict):
            return value, None
        return {}, "Action Input 必须是 JSON 对象"
    except json.JSONDecodeError as exc:
        return {}, f"Action Input JSON 解析失败: {exc}"


def _parse_action_line(rest: str) -> ReActAction:
    """Parse an ``Action:`` line: ``name`` or ``name({...})``."""
    rest = (rest or "").strip().strip("`").strip()
    inline = re.match(r"^([A-Za-z_][\w\-]*)\s*\((.*)\)\s*$", rest, re.DOTALL)
    if inline:
        name = inline.group(1)
        raw_input = inline.group(2).strip()
        if raw_input:
            arguments, error = _extract_json(raw_input)
        else:
            arguments, error = {}, None
        return ReActAction(name=name, arguments=arguments, raw_input=raw_input, error=error)
    parts = rest.split(None, 1)
    name = parts[0].strip().rstrip(",.;，。；") if parts else ""
    raw_input = parts[1].strip() if len(parts) > 1 else ""
    arguments, error = _extract_json(raw_input) if raw_input else ({}, None)
    return ReActAction(name=name, arguments=arguments, raw_input=raw_input, error=error)


def parse_react_trace(text: str) -> ReActTrace | None:
    """Parse a complete model message into a ReAct trace.

    Returns ``None`` when no ReAct keyword appears at all (plain prose —
    the caller should pass the message through untouched).
    """
    trace = ReActTrace()
    saw_keyword = False
    current_thought: list[str] = []
    pending_action: ReActAction | None = None
    in_final = False
    final_lines: list[str] = []

    def flush_thought() -> None:
        if current_thought:
            thought = "\n".join(current_thought).strip()
            if thought:
                trace.thoughts.append(thought[:REACT_MAX_THOUGHT_LEN])
            current_thought.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _KEYWORD_LINE_RE.match(line)
        if match:
            saw_keyword = True
            kind = match.group(1).strip().lower()
            rest = match.group(2)

            def close_pending() -> None:
                nonlocal pending_action
                if pending_action is not None:
                    trace.actions.append(pending_action)
                    pending_action = None

            if kind == "thought":
                flush_thought()
                close_pending()
                current_thought = [rest]
            elif kind == "action":
                flush_thought()
                close_pending()
                pending_action = _parse_action_line(rest)
            elif kind == "action input":
                if pending_action is None:
                    continue
                pending_action.raw_input = rest.strip()
                pending_action.arguments, pending_action.error = _extract_json(
                    pending_action.raw_input
                )
            elif kind == "observation":
                flush_thought()
                close_pending()
            elif kind == "final answer":
                flush_thought()
                close_pending()
                in_final = True
                final_lines = [rest]
            continue
        if in_final:
            final_lines.append(line)
        elif current_thought:
            current_thought.append(line)
        else:
            trace.prose.append(line)

    flush_thought()
    if pending_action is not None:
        trace.actions.append(pending_action)
    if final_lines:
        trace.final_answer = "\n".join(final_lines).strip()
    return trace if saw_keyword else None


def _clean_react_text(trace: ReActTrace) -> str:
    """The user-visible text of a finished trace (scaffolding removed)."""
    if trace.final_answer is not None:
        return trace.final_answer
    return "\n".join(trace.prose).strip()


# --- streaming filter -----------------------------------------------------

_SECTION_BY_KEYWORD = {
    "thought": "thought",
    "action": "suppressed",
    "action input": "suppressed",
    "observation": "suppressed",
    "final answer": "final",
}


class ReActStreamProcessor:
    """Incremental classifier for ReAct text tokens at the SSE layer.

    Emits ``{"type": "think" | "message", "content": str}`` events. The
    ``Action``/``Action Input``/``Observation`` scaffolding is suppressed;
    everything after a ``Final Answer:`` marker streams as ``message``.
    """

    def __init__(self) -> None:
        self._hold = ""
        self._line_start = True
        # None | "prose" | "thought" | "suppressed" | "final"
        self._section: str | None = None

    def push(self, chunk: str) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        for ch in chunk:
            if self._section == "final":
                events.append({"type": "message", "content": ch})
                continue
            if self._line_start:
                self._hold += ch
                if ch == "\n":
                    self._finish_line(events)
                    continue
                kind = self._classify_hold()
                if kind == "pending":
                    continue
                if kind == "prose":
                    # Non-keyword line: keep the current section for
                    # multi-line Thought/Final Answer continuation.
                    if self._section == "thought":
                        events.append({"type": "think", "content": self._hold})
                    elif self._section == "suppressed":
                        pass
                    else:
                        events.append({"type": "message", "content": self._hold})
                    self._hold = ""
                    self._line_start = False
                    continue
                # Keyword matched: switch section, drop the marker itself.
                self._section = _SECTION_BY_KEYWORD[kind]
                self._hold = ""
                self._line_start = False
                continue
            # Mid-line: emit per the current section.
            if self._section == "thought":
                events.append({"type": "think", "content": ch})
            elif self._section == "suppressed":
                pass
            else:
                events.append({"type": "message", "content": ch})
            if ch == "\n":
                self._line_start = True
        return events

    def flush(self) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        if self._hold:
            if self._section == "thought":
                events.append({"type": "think", "content": self._hold})
            elif self._section != "suppressed":
                events.append({"type": "message", "content": self._hold})
            self._hold = ""
        return events

    def _finish_line(self, events: list[dict[str, str]]) -> None:
        # A complete line arrived while holding at line start. The trailing
        # newline is dropped for keyword sections (scaffolding) and kept for
        # visible text so the markdown rendering is unchanged.
        hold = self._hold[:-1]
        self._hold = ""
        self._line_start = True
        if not hold:
            return
        kind = self._classify_hold_text(hold)
        if kind == "pending":
            kind = "prose"
        if kind == "prose":
            if self._section == "thought":
                events.append({"type": "think", "content": hold + "\n"})
            elif self._section != "suppressed":
                events.append({"type": "message", "content": hold + "\n"})
            return
        self._section = _SECTION_BY_KEYWORD[kind]

    def _classify_hold(self) -> str | None:
        return self._classify_hold_text(self._hold)

    @staticmethod
    def _classify_hold_text(hold: str) -> str | None:
        """Classify text held at line start.

        Returns a keyword, ``"prose"``, or ``"pending"`` (need more chars).
        """
        stripped = hold.lower().lstrip()
        if not stripped:
            return "pending"
        for keyword in _KEYWORDS:
            if stripped.startswith(keyword):
                rest = stripped[len(keyword) :]
                if rest == "":
                    return "pending"
                if rest[0] in ":：":
                    return keyword
                if rest[0] in " \t":
                    remainder = rest.lstrip()
                    if remainder == "":
                        return "pending"
                    if remainder[0] in ":：":
                        return keyword
                    return "prose"
                return "prose"
        for keyword in _KEYWORDS:
            if keyword.startswith(stripped):
                return "pending"
        return "prose"


# --- execution bridge -----------------------------------------------------


def _rewritten(
    message: AIMessage,
    *,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> AIMessage:
    kwargs: dict[str, Any] = {}
    if message.usage_metadata:
        kwargs["usage_metadata"] = message.usage_metadata
    if message.additional_kwargs:
        kwargs["additional_kwargs"] = dict(message.additional_kwargs)
    if message.response_metadata:
        kwargs["response_metadata"] = dict(message.response_metadata)
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        id=message.id,
        **kwargs,
    )


class ReActParseMiddleware(AgentMiddleware):
    """Strip tools from the model binding and translate the text ReAct trace
    into standard ``tool_calls`` so the rest of the graph runs unchanged."""

    name = "react_parse"

    def _rewrite_response(self, request: Any, response: ModelResponse) -> ModelResponse:
        if not response.result:
            return response
        message = response.result[0]
        if not isinstance(message, AIMessage):
            return response
        text = _content_text(message.content) if message.content else ""
        if not text:
            return response
        trace = parse_react_trace(text)
        if trace is None:
            return response

        if not trace.actions:
            # Pure text answer: strip the scaffold (Final Answer prefix,
            # stray Thought lines) so history matches what the user saw.
            new_content = _clean_react_text(trace)
            if new_content == text:
                return response
            return ModelResponse(
                result=[_rewritten(message, content=new_content)],
                structured_response=response.structured_response,
            )

        calls: list[dict[str, Any]] = []
        for index, action in enumerate(trace.actions):
            if not action.name:
                continue
            # Malformed Action Input yields empty args; the tool's schema
            # validation then surfaces an error the model can retry from.
            calls.append(
                {
                    "id": f"react_{index}_{uuid4().hex[:8]}",
                    "name": action.name,
                    "args": action.arguments,
                    "type": "function",
                }
            )
        if not calls:
            return response
        rewritten = _rewritten(message, content="", tool_calls=calls)
        return ModelResponse(
            result=[rewritten, *response.result[1:]],
            structured_response=response.structured_response,
        )

    def wrap_model_call(
        self, request: Any, handler: Any
    ) -> ModelResponse:
        # The model must produce plain text, so never bind tools.
        if request.tools:
            request = request.override(tools=[])
        return self._rewrite_response(request, handler(request))

    async def awrap_model_call(
        self, request: Any, handler: Any
    ) -> ModelResponse:
        # The model must produce plain text, so never bind tools.
        if request.tools:
            request = request.override(tools=[])
        response = await handler(request)
        return self._rewrite_response(request, response)
