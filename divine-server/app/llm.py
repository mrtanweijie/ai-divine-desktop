from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, AsyncIterator

import httpx

from .config import settings_store

logger = logging.getLogger("divine.llm")

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


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if value:
                    parts.append(str(value))
        return "".join(parts)
    return str(content) if content else ""


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
        logger.info(
            "DeepSeek request model=%s messages=%d tools=%d think=%s",
            payload.get("model"),
            len(messages),
            len(tools or []),
            think,
        )
        headers = {
            "Authorization": f"Bearer {self.settings.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(120.0, connect=20.0)
        dsml = DsmlStreamProcessor()
        event_count = 0
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")[:500]
                    logger.warning(
                        "DeepSeek API error status=%s body=%s",
                        response.status_code,
                        body,
                    )
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
                    if delta.get("reasoning_content"):
                        event_count += 1
                        yield {
                            "type": "think",
                            "content": delta["reasoning_content"],
                        }
                    if delta.get("content"):
                        for event in dsml.push(delta["content"]):
                            event_count += 1
                            yield event
                    for tool_call in delta.get("tool_calls") or []:
                        function = tool_call.get("function") or {}
                        event_count += 1
                        yield {
                            "type": "tool_call",
                            "index": tool_call.get("index", 0),
                            "id": tool_call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments") or "",
                        }
                for event in dsml.flush():
                    event_count += 1
                    yield event
        logger.info(
            "DeepSeek stream end model=%s events=%d",
            payload.get("model"),
            event_count,
        )


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
        last_tool = (
            self._last_tool_result(messages)
            if messages and messages[-1].get("role") == "tool"
            else None
        )
        if last_tool:
            if last_tool.get("success") and last_tool.get("file_name"):
                answer = (
                    f"已完成：{last_tool.get('file_name')} 已保存，"
                    "可以从工具卡片打开所在目录。"
                )
            elif last_tool.get("success") and (last_tool.get("data") or {}).get(
                "option"
            ):
                answer = "已根据分析结果生成图表，图表会直接显示在消息里。"
            else:
                answer = last_tool.get("message") or "工具执行失败"
            for piece in self._chunks(answer):
                yield {"type": "message", "content": piece}
            return
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
        wants_svg = any(
            word in lowered
            for word in ("svg", "矢量图", "插画", "图标", "角色图", "位图")
        )
        wants_svg_edit = any(
            word in lowered
            for word in ("修改svg", "编辑svg", "改svg", "修改矢量图", "编辑矢量图")
        )
        wants_svg_export = any(
            word in lowered
            for word in (
                "svg转png",
                "svg 转 png",
                "导出svg",
                "svg导出",
                "svg转位图",
                "位图",
            )
        )
        wants_svg_batch = any(
            word in lowered
            for word in (
                "ios 图标",
                "ios图标",
                "多尺寸",
                "多个尺寸",
                "全套图标",
                "app 图标",
                "app图标",
            )
        )
        wants_presentation = any(
            word in lowered
            for word in ("ppt", "幻灯片", "演示文稿", "presentation")
        )
        wants_mermaid_export = any(
            word in lowered
            for word in (
                "导出流程图",
                "保存流程图",
                "导出 mermaid",
                "保存 mermaid",
                "导出mermaid",
                "保存mermaid",
                "mmd 文件",
                "mmd文件",
            )
        )
        wants_chart = any(
            word in lowered
            for word in (
                "图表",
                "画图",
                "折线图",
                "柱状图",
                "饼图",
                "散点图",
                "趋势图",
                "占比图",
                "chart",
            )
        )
        wants_web = any(
            word in lowered
            for word in ("网页", "网站", "抓取", "浏览", "url", "http")
        )
        wants_batch_fetch = any(
            word in lowered
            for word in (
                "批量抓取",
                "多个数据源",
                "多数据源",
                "多个指数",
                "几个指数",
                "指数对比",
                "多个网站",
            )
        )
        if wants_svg and wants_svg_edit:
            for tool in tools:
                if tool.get("function", {}).get("name") == "edit_svg":
                    return tool
        if wants_svg and wants_svg_batch:
            for tool in tools:
                if tool.get("function", {}).get("name") == "svg_to_png_batch":
                    return tool
        if wants_svg and (wants_svg_export or "png" in lowered or "导出" in question):
            for tool in tools:
                if tool.get("function", {}).get("name") == "svg_to_png":
                    return tool
        if wants_svg:
            for tool in tools:
                if tool.get("function", {}).get("name") == "draw_svg":
                    return tool
        if wants_mermaid_export:
            for tool in tools:
                if tool.get("function", {}).get("name") == "mermaid_export":
                    return tool
        if wants_chart:
            for tool in tools:
                if tool.get("function", {}).get("name") == "generate_chart":
                    return tool
        if wants_image:
            for tool in tools:
                if tool.get("function", {}).get("name") == "read_image":
                    return tool
        if wants_presentation:
            for tool in tools:
                if tool.get("function", {}).get("name") == "presentation":
                    return tool
        if wants_batch_fetch:
            for tool in tools:
                if tool.get("function", {}).get("name") == "web_fetch_batch":
                    return tool
        if wants_web:
            for tool in tools:
                if tool.get("function", {}).get("name") == "web_fetch":
                    return tool
        if wants_read:
            for tool in tools:
                if tool.get("function", {}).get("name") == "read_file":
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
        if tool_name == "draw_svg":
            return {
                "title": "小机器人",
                "content": (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" '
                    'viewBox="0 0 320 240">'
                    '<rect id="body" x="90" y="90" width="140" height="110" rx="18" '
                    'fill="#0f766e"/>'
                    '<rect id="head" x="110" y="45" width="100" height="70" rx="16" '
                    'fill="#14b8a6"/>'
                    '<circle id="eye-left" cx="135" cy="80" r="7" fill="#ffffff"/>'
                    '<circle id="eye-right" cx="185" cy="80" r="7" fill="#ffffff"/>'
                    '<rect id="hair" x="118" y="52" width="84" height="10" rx="5" '
                    'fill="#134e4a"/>'
                    '<rect id="arm-left" x="62" y="105" width="28" height="70" rx="10" '
                    'fill="#0d9488"/>'
                    '<rect id="arm-right" x="230" y="105" width="28" height="70" rx="10" '
                    'fill="#0d9488"/>'
                    '</svg>'
                ),
            }
        if tool_name == "describe_svg":
            return {"file_path": "svg/小机器人.svg"}
        if tool_name == "edit_svg":
            return {
                "file_path": "svg/小机器人.svg",
                "content": (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" '
                    'viewBox="0 0 320 240">'
                    '<rect id="body" x="90" y="90" width="140" height="110" rx="18" '
                    'fill="#0f766e"/>'
                    '<rect id="head" x="110" y="45" width="100" height="70" rx="16" '
                    'fill="#14b8a6"/>'
                    '<circle id="eye-left" cx="135" cy="80" r="9" fill="#ffffff"/>'
                    '<circle id="eye-right" cx="185" cy="80" r="9" fill="#ffffff"/>'
                    '<rect id="hair" x="118" y="52" width="84" height="10" rx="5" '
                    'fill="#134e4a"/>'
                    '<rect id="arm-left" x="62" y="105" width="28" height="70" rx="10" '
                    'fill="#0d9488"/>'
                    '<rect id="arm-right" x="230" y="105" width="28" height="70" rx="10" '
                    'fill="#0d9488"/>'
                    '</svg>'
                ),
            }
        if tool_name == "svg_to_png":
            return {
                "file_path": "svg/小机器人.svg",
                "width": 640,
                "height": 480,
            }
        if tool_name == "svg_to_png_batch":
            return {
                "file_path": "svg/小机器人.svg",
                "prefix": "简记app图标",
                "sizes": [1024, 180, 167, 152, 120, 87, 80, 76, 60, 58, 40, 29, 20],
            }
        if tool_name == "generate_chart":
            return {
                "title": "AI Divine 能力分布",
                "option": {
                    "title": {"text": "AI Divine 能力分布", "left": 12},
                    "tooltip": {"trigger": "axis"},
                    "legend": {"top": 8, "right": 12},
                    "grid": {"left": 40, "right": 20, "top": 40, "bottom": 48},
                    "xAxis": {
                        "type": "category",
                        "data": ["文件分析", "文档生成", "RAG 检索", "定时任务", "日历"],
                    },
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "name": "能力评分",
                            "type": "bar",
                            "data": [88, 95, 76, 82, 91],
                            "itemStyle": {"borderRadius": [6, 6, 0, 0]},
                        }
                    ],
                },
            }
        if tool_name == "mermaid_export":
            return {
                "title": "AI Divine 处理流程",
                "content": (
                    "flowchart LR\n"
                    "  A[接收需求] --> B{是否复杂}\n"
                    "  B -- 是 --> C[拆子任务]\n"
                    "  B -- 否 --> D[直接回答]\n"
                    "  C --> E[并行调用工具]\n"
                ),
                "path": "",
            }
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
        if tool_name == "presentation":
            return {
                "title": "AI Divine 产品介绍",
                "slides": [
                    {
                        "heading": "项目背景",
                        "body": "本地优先的桌面 AI 助手\n支持文件分析、文档生成和工具调用",
                    },
                    {
                        "heading": "核心能力",
                        "body": "流式对话\n文件问答\nWord / Excel / Markdown / PPT 生成",
                    },
                    {
                        "heading": "下一步计划",
                        "body": "接入更多本地工具与 MCP 能力",
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
        if tool_name == "web_fetch":
            for token in question.split():
                if token.startswith("http"):
                    return {"url": token.strip("，。、,;；")}
            return {"url": "https://example.com"}
        if tool_name == "web_fetch_batch":
            return {
                "urls": [
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,30,qfq",
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz399001,day,,,30,qfq",
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz399006,day,,,30,qfq",
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,day,,,30,qfq",
                ],
                "max_results": 4,
            }
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
        if any(
            word in question
            for word in ("画一个流程", "画流程", "流程图", "工作流", "处理链路", "步骤图")
        ):
            return (
                "这是这个流程的可视化表示：\n\n"
                "```mermaid\n"
                "flowchart LR\n"
                "  A[接收需求] --> B{是否复杂}\n"
                "  B -- 是 --> C[拆子任务]\n"
                "  B -- 否 --> D[直接回答]\n"
                "  C --> E[并行调用工具]\n"
                "```"
            )
        if "工具" in question or "tool" in question.lower():
            return (
                "当前已注册多类本地工具：`word_document` 生成 Word 文档，`spreadsheet` "
                "生成 Excel 表格，`notes` 生成 Markdown 笔记，`mermaid_export` 导出流程图，"
                "`generate_chart` 生成图表。工具状态会以卡片形式出现在消息流中。"
            )
        return (
            "我已经收到你的问题。当前处于本地演示模式：在 `.env` 或设置中填入 "
            "DeepSeek API Key 后，会切换到真实模型流式回答。"
        )

    @staticmethod
    def _last_tool_result(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        for message in reversed(messages):
            if message.get("role") != "tool":
                continue
            try:
                result = json.loads(message.get("content") or "{}")
            except json.JSONDecodeError:
                return {"success": False, "message": "工具执行失败"}
            return result if isinstance(result, dict) else {"success": False}
        return None


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
