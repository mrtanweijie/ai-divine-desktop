"""LangChain chat model adapters used by the agent runtime."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import SimpleChatModel

from ..config import settings_store
from .content import _content_text
from .dsml import DsmlStreamProcessor
from .legacy import MockLLM
from .thinking import normalize_reasoning_effort, thinking_extra_body


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
                    for item, original in zip(
                        payload.get("messages", []), originals
                    ):
                        if isinstance(original, AIMessage):
                            reasoning = original.additional_kwargs.get(
                                "reasoning_content"
                            )
                            if reasoning:
                                item["reasoning_content"] = reasoning
                        if isinstance(original, AIMessage) and item.get(
                            "tool_calls"
                        ):
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
                except Exception:
                    pass
                return payload

        self.settings = settings_store.load()
        model = self.settings.get("model") or "deepseek-v4-flash"
        if model in ("", "local", "mock"):
            model = "deepseek-v4-flash"
        # DeepSeek thinking mode ignores sampling params (temperature, top_p,
        # presence/frequency penalty), so only send temperature when thinking
        # is disabled.
        self.effort = normalize_reasoning_effort(
            effort if effort is not None
            else self.settings.get("reasoning_effort")
        )
        self.llm = ReasoningChatDeepSeek(
            model=model,
            api_key=self.settings.get("api_key"),
            temperature=0.7 if not think else None,
            reasoning_effort=self.effort if think else None,
            streaming=True,
            extra_body=thinking_extra_body(think),
        )

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
