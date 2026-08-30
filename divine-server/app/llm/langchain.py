"""LangChain chat model adapters used by the agent runtime."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from langchain_core.language_models.chat_models import SimpleChatModel

from ..config import settings_store
from .content import _content_text
from .dsml import DsmlStreamProcessor
from .legacy import MockLLM
from .thinking import normalize_reasoning_effort, thinking_extra_body

logger = logging.getLogger(__name__)


def _resolve_int(value: Any, default: int) -> int:
    """Best-effort positive-int coercion for settings fields (max_retries 等)。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _network_kwargs(entry: dict[str, Any]) -> dict[str, Any]:
    """Explicit network-level kwargs shared by all real providers.

    ``max_retries`` 显式化（LangChain/OpenAI 客户端默认 2，避免随版本漂移）；
    ``timeout`` 未配置时不下发，保留 openai 客户端自身默认，行为零变化。
    """
    kwargs: dict[str, Any] = {
        "max_retries": _resolve_int(entry.get("max_retries"), 2),
    }
    timeout = entry.get("timeout")
    if timeout not in (None, ""):
        try:
            kwargs["request_timeout"] = float(timeout)
        except (TypeError, ValueError):
            logger.warning("忽略非法的 timeout 设置: %r", timeout)
    return kwargs


def _dedupe_tool_call_ids(messages: list[dict[str, Any]]) -> None:
    """Re-assign duplicate assistant ``tool_call`` ids and sync ToolMessages.

    Some reasoning providers (e.g. MiniMax) reject requests whose historical
    assistant tool calls carry duplicate ids with
    ``invalid params, duplicate tool_call id``. LangGraph replays previous
    turns; if a model ever emitted two calls with the same id (or a snapshot
    got duplicated), the whole history becomes un-sendable. Each duplicated
    occurrence (in order) gets a fresh id and the matching ``tool`` messages
    are updated positionally so the conversation stays consistent.
    """
    # 1. Collect assistant call ids in order; mark which occurrences are dupes.
    call_ids: list[str] = []
    for item in messages:
        for call in item.get("tool_calls") or []:
            cid = call.get("id")
            if cid:
                call_ids.append(cid)
    seen: set[str] = set()
    replacement: dict[tuple[str, int], str] = {}
    occurrence: dict[str, int] = {}
    for cid in call_ids:
        occurrence[cid] = occurrence.get(cid, 0) + 1
        if cid in seen:
            replacement[(cid, occurrence[cid])] = (
                f"call_{uuid.uuid4().hex[:24]}"
            )
        else:
            seen.add(cid)
    if not replacement:
        return
    # 2. Rewrite assistant tool calls positionally.
    occ: dict[str, int] = {}
    for item in messages:
        for call in item.get("tool_calls") or []:
            cid = call.get("id")
            if not cid:
                continue
            occ[cid] = occ.get(cid, 0) + 1
            new_id = replacement.get((cid, occ[cid]))
            if new_id:
                call["id"] = new_id
    # 3. Rewrite matching tool messages positionally.
    tool_occ: dict[str, int] = {}
    for item in messages:
        if item.get("role") == "tool":
            tid = item.get("tool_call_id")
            if not tid:
                continue
            tool_occ[tid] = tool_occ.get(tid, 0) + 1
            new_id = replacement.get((tid, tool_occ[tid]))
            if new_id:
                item["tool_call_id"] = new_id


class MockChatModel(SimpleChatModel):
    """LangChain chat model used by create_agent when no API key is configured."""

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def _call(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> str:
        from langchain_core.messages import HumanMessage

        question = next(
            (
                message.content
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        return MockLLM._answer(str(question or ""))

    def bind_tools(
        self,
        tools: list[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "MockChatModel":
        return self

class ChatDeepSeekProvider:
    def __init__(
        self,
        think: bool = False,
        effort: str | None = None,
        entry: dict[str, Any] | None = None,
    ) -> None:
        from langchain_core.messages import (
            AIMessage,
            ToolMessage,
            convert_to_messages,
        )
        from langchain_deepseek import ChatDeepSeek

        class ReasoningChatDeepSeek(ChatDeepSeek):
            def _get_request_payload(
                self,
                input_: Any,
                *,
                stop: list[str] | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                payload = super()._get_request_payload(
                    input_, stop=stop, **kwargs
                )
                try:
                    originals = convert_to_messages(input_)
                    tool_result_ids = {
                        getattr(original, "tool_call_id", "") or ""
                        for original in originals
                        if isinstance(original, ToolMessage)
                    }
                    messages = payload.get("messages", [])
                    drop_indices: set[int] = set()
                    for index, (item, original) in enumerate(
                        zip(messages, originals)
                    ):
                        if not isinstance(original, AIMessage):
                            continue
                        reasoning = original.additional_kwargs.get(
                            "reasoning_content"
                        )
                        if reasoning:
                            item["reasoning_content"] = reasoning
                        if item.get("tool_calls"):
                            valid_calls = [
                                call
                                for call in item["tool_calls"]
                                if isinstance(call, dict)
                                and call.get("id") in tool_result_ids
                            ]
                            if valid_calls:
                                item["tool_calls"] = valid_calls
                            else:
                                item.pop("tool_calls", None)
                        # 丢弃既无 content 也无 tool_calls 的 assistant 消息
                        # （例如模型偶发的空回复，或工具调用被过滤后残留），
                        # DeepSeek 会以 400 拒绝这类消息。
                        if not (
                            (item.get("content") or "").strip()
                            or item.get("tool_calls")
                        ):
                            drop_indices.add(index)
                    if drop_indices:
                        payload["messages"] = [
                            message
                            for index, message in enumerate(messages)
                            if index not in drop_indices
                        ]
                except Exception:
                    pass
                return payload

        self.settings = settings_store.load()
        # `entry` is a resolved model configuration (from the multi-model
        # settings list); when absent, fall back to the legacy top-level fields.
        entry = entry if entry is not None else self.settings
        model = entry.get("model") or "deepseek-v4-flash"
        if model in ("", "local", "mock"):
            model = "deepseek-v4-flash"
        # DeepSeek thinking mode ignores sampling params (temperature, top_p,
        # presence/frequency penalty), so only send temperature when thinking
        # is disabled.
        self.effort = normalize_reasoning_effort(
            effort if effort is not None
            else self.settings.get("reasoning_effort")
        )
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": entry.get("api_key"),
            "temperature": 0.7 if not think else None,
            "reasoning_effort": self.effort if think else None,
            "streaming": True,
            "extra_body": thinking_extra_body(think),
        }
        base_url = str(entry.get("base_url") or "").strip()
        if base_url:
            llm_kwargs["base_url"] = base_url
        llm_kwargs.update(_network_kwargs(entry))
        logger.info(
            "LLM provider 初始化: provider=deepseek model=%s base_url=%s "
            "think=%s effort=%s max_retries=%s timeout=%s",
            model,
            base_url or "(默认)",
            think,
            self.effort,
            llm_kwargs["max_retries"],
            llm_kwargs.get("request_timeout"),
        )
        self.llm = ReasoningChatDeepSeek(**llm_kwargs)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        converted: list[Any] = []
        for item in messages:
            role = item.get("role")
            content = item.get("content") or ""
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                tool_calls = item.get("tool_calls")
                reasoning = item.get("reasoning_content") or ""
                additional_kwargs = (
                    {"reasoning_content": reasoning} if reasoning else {}
                )
                if tool_calls:
                    converted_tool_calls = []
                    for call in tool_calls:
                        function = call.get("function") or {}
                        try:
                            args = json.loads(function.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        converted_tool_calls.append(
                            {
                                "id": call.get("id") or "",
                                "name": function.get("name") or "",
                                "args": args,
                                "type": "function",
                            }
                        )
                    converted.append(
                        AIMessage(
                            content=content,
                            tool_calls=converted_tool_calls,
                            additional_kwargs=additional_kwargs,
                        )
                    )
                else:
                    converted.append(
                        AIMessage(
                            content=content,
                            additional_kwargs=additional_kwargs,
                        )
                    )
            elif role == "tool":
                converted.append(
                    ToolMessage(
                        content=content,
                        tool_call_id=item.get("tool_call_id") or "",
                    )
                )
            else:
                converted.append(HumanMessage(content=content))

        llm = self.llm
        if think is not None:
            # Keep the toggle symmetric: an explicit think flag overrides the
            # constructor setting in both directions (enable *and* disable).
            bind_kwargs: dict[str, Any] = {
                "extra_body": thinking_extra_body(think)
            }
            if think:
                bind_kwargs["reasoning_effort"] = self.effort
            llm = llm.bind(**bind_kwargs)
        bound = llm.bind_tools(tools) if tools else llm
        dsml = DsmlStreamProcessor()
        calls: dict[int, dict[str, str]] = {}
        async for chunk in bound.astream(converted):
            reasoning = chunk.additional_kwargs.get("reasoning_content")
            if reasoning:
                yield {"type": "think", "content": reasoning}
            content = _content_text(chunk.content)
            if content:
                for event in dsml.push(content):
                    yield event
            for call_chunk in getattr(chunk, "tool_call_chunks", []) or []:
                index = int(call_chunk.get("index") or 0)
                entry = calls.setdefault(
                    index, {"id": "", "name": "", "arguments": ""}
                )
                if call_chunk.get("id"):
                    entry["id"] = call_chunk["id"]
                if call_chunk.get("name"):
                    entry["name"] = call_chunk["name"]
                entry["arguments"] += call_chunk.get("args") or ""

        for event in dsml.flush():
            yield event

        for index, call in calls.items():
            yield {
                "type": "tool_call",
                "index": index,
                "id": call["id"],
                "name": call["name"],
                "arguments": call["arguments"],
            }


def _is_glm_always_think(model: str) -> bool:
    """GLM-5.x 文本旗舰（glm-5 / 5.1 / 5.2 / 5.3）始终启用思考，
    不支持 thinking.type: "disabled"（见官方文档 glm-5.3）。
    glm-5v-turbo 等视觉模型不在此列。
    """
    m = str(model or "").strip().lower()
    if not m.startswith("glm-5"):
        return False
    # 排除带 v 的视觉变体
    return "-5v" not in m and not m.startswith("glm-5v")


class OpenAIChatProvider:
    """LangChain adapter for OpenAI-compatible endpoints (mimo, etc.).
    Uses langchain_openai.ChatOpenAI directly — no DeepSeek-specific
    reasoning/thinking extensions."""

    def __init__(
        self,
        think: bool = False,
        effort: str | None = None,
        entry: dict[str, Any] | None = None,
    ) -> None:
        from langchain_openai import ChatOpenAI

        class DedupToolCallChatOpenAI(ChatOpenAI):
            """ChatOpenAI that rewrites duplicate tool_call ids before sending.

            Some providers (MiniMax) hard-reject history with duplicated
            assistant tool_call ids; fix them at the request payload level.
            """

            def _get_request_payload(
                self,
                input_: Any,
                *,
                stop: list[str] | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                payload = super()._get_request_payload(
                    input_, stop=stop, **kwargs
                )
                try:
                    _dedupe_tool_call_ids(payload.get("messages", []))
                except Exception:  # noqa: BLE001 — 清理失败不阻断请求
                    pass
                return payload

        settings = settings_store.load()
        entry = entry if entry is not None else settings
        model = entry.get("model") or "gpt-4o-mini"
        if model in ("", "local", "mock"):
            model = "gpt-4o-mini"
        base_url = str(entry.get("base_url") or "").strip()
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": entry.get("api_key"),
            "streaming": True,
            "temperature": 0.7,
        }
        if base_url:
            llm_kwargs["base_url"] = base_url
        llm_kwargs.update(_network_kwargs(entry))
        logger.info(
            "LLM provider 初始化: provider=openai model=%s base_url=%s "
            "max_retries=%s timeout=%s",
            model,
            base_url or "(默认)",
            llm_kwargs["max_retries"],
            llm_kwargs.get("request_timeout"),
        )
        # GLM-5.x 文本旗舰始终启用思考，必须显式附带 thinking 参数，
        # 否则请求会被拒绝（官方文档：迁移时需将 thinking.type 设为 enabled）。
        if _is_glm_always_think(model):
            effort = (effort or "").strip().lower()
            reasoning = effort if effort in ("low", "high", "max") else "high"
            llm_kwargs["extra_body"] = {
                "thinking": {"type": "enabled"},
                "reasoning_effort": reasoning,
            }
        self.llm = DedupToolCallChatOpenAI(**llm_kwargs)
