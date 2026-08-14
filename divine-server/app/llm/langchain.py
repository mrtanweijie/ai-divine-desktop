"""LangChain chat model adapters used by the agent runtime."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import SimpleChatModel

from ..config import settings_store
from .content import _content_text
from .dsml import DsmlStreamProcessor
from .legacy import MockLLM

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
    def __init__(self) -> None:
        from langchain_core.messages import AIMessage, convert_to_messages
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
                    for item, original in zip(
                        payload.get("messages", []), originals
                    ):
                        if isinstance(original, AIMessage):
                            reasoning = original.additional_kwargs.get(
                                "reasoning_content"
                            )
                            if reasoning:
                                item["reasoning_content"] = reasoning
                except Exception:
                    pass
                return payload

        self.settings = settings_store.load()
        model = self.settings.get("model") or "deepseek-v4-flash"
        if model in ("", "local", "mock"):
            model = "deepseek-v4-flash"
        self.llm = ReasoningChatDeepSeek(
            model=model,
            api_key=self.settings.get("api_key"),
            temperature=0.7,
            streaming=True,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = False,
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

        bound = self.llm.bind_tools(tools) if tools else self.llm
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
