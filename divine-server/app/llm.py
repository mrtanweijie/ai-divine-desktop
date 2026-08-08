from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .config import settings_store


class DeepSeekLLM:
    def __init__(self) -> None:
        self.settings = settings_store.load()

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.settings.get("model") or "deepseek-v4-flash",
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        url = (self.settings.get("base_url") or "https://api.deepseek.com").rstrip(
            "/"
        ) + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(120.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")[:500]
                    raise RuntimeError(
                        f"模型接口返回 {response.status_code}: {body}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    if think and delta.get("reasoning_content"):
                        yield {
                            "type": "think",
                            "content": delta["reasoning_content"],
                        }
                    if delta.get("content"):
                        yield {"type": "message", "content": delta["content"]}
                    for tool_call in delta.get("tool_calls") or []:
                        function = tool_call.get("function") or {}
                        yield {
                            "type": "tool_call",
                            "index": tool_call.get("index", 0),
                            "id": tool_call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments") or "",
                        }


class MockLLM:
    """Local demo provider so the app is usable before a DeepSeek key exists."""

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        question = next(
            (
                m.get("content", "")
                for m in reversed(messages)
                if m.get("role") == "user"
            ),
            "",
        )
        tool = self._pick_tool(question, tools or [])
        if think:
            for piece in self._chunks(
                "先判断用户想要什么，再选择最合适的工具。这个请求适合用本地工具完成。"
            ):
                yield {"type": "think", "content": piece}
        if tool:
            name = tool["function"]["name"]
            args = self._mock_args(name, question)
            yield {
                "type": "tool_call",
                "index": 0,
                "id": f"mock_{name}",
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            }
            return
        answer = self._answer(question)
        for piece in self._chunks(answer):
            yield {"type": "message", "content": piece}

    @staticmethod
    def _chunks(text: str):
        step = max(1, len(text) // 24)
        for i in range(0, len(text), step):
            yield text[i : i + step]

    @staticmethod
    def _pick_tool(question: str, tools: list[dict[str, Any]]) -> dict[str, Any] | None:
        lowered = question.lower()
        wants_word = any(word in lowered for word in ("word", "docx", "文档", "合同", "周报"))
        wants_sheet = any(
            word in lowered for word in ("excel", "xlsx", "表格", "电子表格", "数据表")
        )
        wants_note = any(
            word in lowered for word in ("笔记", "note", "markdown", "md 文件", "md文件")
        )
        wants_read = any(
            word in lowered for word in ("读取", "读一下", "read", "文件内容")
        )
        wants_image = any(
            word in lowered for word in ("图片", "image", "png", "jpg", "jpeg", "webp")
        )
        if wants_read:
            for tool in tools:
                if tool.get("function", {}).get("name") == "read_file":
                    return tool
        if wants_image:
            for tool in tools:
                if tool.get("function", {}).get("name") == "read_image":
                    return tool
        for tool in tools:
            name = tool.get("function", {}).get("name", "")
            if wants_word and name == "word_document":
                return tool
            if wants_sheet and name == "spreadsheet":
                return tool
            if wants_note and name == "notes":
                return tool
        return None

    @staticmethod
    def _mock_args(tool_name: str, question: str) -> dict[str, Any]:
        if tool_name == "word_document":
            return {
                "title": "AI Divine 项目周报",
                "sections": [
                    {
                        "heading": "本周进展",
                        "body": "完成了桌面 AI 助手第一版：支持流式对话、会话历史、深度思考和本地工具调用。",
                    },
                    {
                        "heading": "下一步计划",
                        "body": "接入文件问答、剪贴板工具和 RAG 检索，并完成 Tauri 打包分发。",
                    },
                ],
            }
        if tool_name == "spreadsheet":
            return {
                "file_name": "项目进度表.xlsx",
                "headers": ["任务", "负责人", "状态", "完成度"],
                "rows": [
                    ["流式对话", "后端", "完成", "100%"],
                    ["会话管理", "前端", "完成", "100%"],
                    ["工具系统", "后端", "进行中", "60%"],
                    ["桌面打包", "桌面端", "未开始", "0%"],
                ],
            }
        if tool_name == "read_file":
            return {
                "file_path": "notes/AI_Divine_使用笔记.md",
            }
        if tool_name == "read_image":
            for marker in ("图片本地路径：", "图片本地路径:"):
                start = question.find(marker)
                if start != -1:
                    rest = question[start + len(marker) :].strip().splitlines()[0]
                    return {"file_path": rest.strip()}
            return {"file_path": ""}
        return {
            "title": "AI Divine 使用笔记",
            "content": (
                "AI Divine 是本地优先的桌面 AI 助手。\n\n"
                "- 所有会话和工具产物默认保存在本地\n"
                "- 支持深度思考和工具调用状态可视化\n"
                "- 工具脚本通过 JSON stdin/stdout 与后端通信"
            ),
        }

    @staticmethod
    def _answer(question: str) -> str:
        if "你好" in question or "hello" in question.lower():
            return (
                "你好，我是 AI Divine 本地助手。我可以回答问题，也可以帮你生成 "
                "Word 文档、Excel 表格和 Markdown 笔记。"
            )
        if "工具" in question or "tool" in question.lower():
            return (
                "当前已注册三类工具：`word_document` 生成 Word 文档，`spreadsheet` "
                "生成 Excel 表格，`notes` 生成 Markdown 笔记。工具状态会以卡片形式出现在消息流中。"
            )
        return (
            "我已经收到你的问题。当前处于本地演示模式：在 `.env` 或设置中填入 "
            "DeepSeek API Key 后，会切换到真实模型流式回答。"
        )


class ChatDeepSeekProvider:
    def __init__(self) -> None:
        from langchain_deepseek import ChatDeepSeek

        self.settings = settings_store.load()
        model = self.settings.get("model") or "deepseek-v4-flash"
        if model in ("", "local", "mock"):
            model = "deepseek-v4-flash"
        self.llm = ChatDeepSeek(
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
                        AIMessage(content=content, tool_calls=converted_tool_calls)
                    )
                else:
                    converted.append(AIMessage(content=content))
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
        calls: dict[int, dict[str, str]] = {}
        async for chunk in bound.astream(converted):
            reasoning = chunk.additional_kwargs.get("reasoning_content")
            if reasoning:
                yield {"type": "think", "content": reasoning}
            content = chunk.content
            if content:
                yield {"type": "message", "content": content}
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

        for index, call in calls.items():
            yield {
                "type": "tool_call",
                "index": index,
                "id": call["id"],
                "name": call["name"],
                "arguments": call["arguments"],
            }
