"""本地聊天子系统：简单任务本地模型直答 + 启发式分流。

从 api/chat.py 拆分而来：本地模型直答（流式/非流式）、指代/选项补全、
本地拒答护栏。分流判定的启发式检测器已收口到
agent/intent/local_task（本文件 re-export 以维持引用链）。

对外接口：
- ``stream_local_chat`` / ``_local_answer`` / ``_build_local_chat_messages``：本地直答执行
- ``_detect_local_task`` / ``_detect_qa`` / ``_is_simple_translation`` 等检测器：分流判定
- ``_expand_referential_followup`` / ``_expand_choice_selection`` / ``_replace_last_user``：
  多轮上下文补全
- ``_is_local_refusal`` / ``_is_list_request`` / ``_has_list_items`` / ``_is_realtime_request``：
  护栏
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Callable

from .. import db
from ..sse import error_event, sse_event

# 本地能力路由启发式已收口到 agent/intent/local_task（行为不变）；
# 这里再导出以维持 chat.py 的 re-export 链与既有测试引用。
from ..agent.intent.local_task import (  # noqa: F401
    _ACTION_WORDS,
    _AI_ASKING_MARKERS,
    _CHAT_MARKERS,
    _CHAT_TRIM_CHARS,
    _DOC_TOOL_MARKERS,
    _ENTITY_KNOWLEDGE_MARKERS,
    _EXTRACT_MARKERS,
    _LOCAL_TASK_DETECTORS,
    _LOCAL_TASK_PROMPTS,
    _NUMERIC_FACT_MARKERS,
    _QA_FALLBACK_MARKERS,
    _QUESTION_MARKERS,
    _REALTIME_KEYWORDS,
    _REALTIME_PATTERNS,
    _REWRITE_MARKERS,
    _SMALL_LANGS,
    _ai_asking_hint,
    _detect_calc,
    _detect_extract,
    _detect_local_task,
    _detect_qa,
    _detect_rewrite,
    _detect_simple_chat,
    _is_realtime_request,
    _is_simple_translation,
)

logger = logging.getLogger("divine.chat.local")



def _local_answer(question: str, system_prompt: str) -> str | None:
    """非流式调用本地模型，返回完整回答；失败/空返回 None。

    知识问答（qa）任务用——需要先看完整回答判断是否"不确定"再决定
    本地交付还是回退云端，流式无法前置判断。
    """
    from ..agent.core import get_manager

    manager = get_manager()
    if not manager.is_ready():
        return None
    import requests

    payload = {
        "model": "local",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
        "max_tokens": 256,
    }
    try:
        r = requests.post(
            f"http://127.0.0.1:{manager.port}/v1/chat/completions",
            json=payload,
            timeout=60.0,
        )
        r.raise_for_status()
        content = str(
            r.json()["choices"][0]["message"]["content"] or ""
        ).strip()
        return content or None
    except Exception:  # noqa: BLE001 — 失败回退云端
        return None


def _build_local_chat_messages(
    question: str,
    history: list[dict[str, Any]],
    locale: str | None,
    ctx_size: int = 4096,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """组装本地模型对话的 messages，按上下文预算裁剪历史。

    修复：history[-12:] 每条 2000 字符全塞会轻松超 4096 ctx，
    llama.cpp 返回 400 exceed_context_size_error。这里用 estimate_tokens
    从新到旧挑选历史，预算 = ctx - 系统提示 - 输出预留（1100 token）。
    ``system_prompt`` 可传任务专用提示（本地能力路由），默认通用助手提示。
    """
    from ..agent.state import estimate_tokens

    lang = "中文" if str(locale or "").startswith("zh") else "English"
    if system_prompt is None:
        system_prompt = (
            f"你是一个乐于助人的 AI 助手，请用{lang}简洁、准确地回答。"
        )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    budget = ctx_size - estimate_tokens(system_prompt) - 1100
    if budget < 256:
        budget = 256

    question = str(question or "").strip()
    history_trim = history[-12:]
    # 最后一条可能是刚保存的当前问题（chat.py 预先 add_message），跳过避免重复
    if history_trim and (
        str(history_trim[-1].get("content") or "").strip() == question
    ):
        history_trim = history_trim[:-1]

    # 从新到旧挑选历史，直到预算不足（至少留 256 token 给当前问题）
    picked: list[dict[str, str]] = []
    for message in reversed(history_trim):
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        content = content[:2000]
        tokens = estimate_tokens(content)
        if budget - tokens < 256:
            break
        budget -= tokens
        picked.append({"role": role, "content": content})
    messages.extend(reversed(picked))

    # 当前问题必放；极端超预算时按比例截断
    q_tokens = estimate_tokens(question)
    if budget < q_tokens and question:
        cut = max(int(len(question) * budget / max(q_tokens, 1)) - 32, 64)
        question = question[:cut]
    messages.append({"role": "user", "content": question})
    return messages


# 小语种（1.5B 训练数据少，容易一本正经地编造）——翻译与问答都排除
_REFUSAL_PATTERNS = (
    # 否定能力 + 动作：无法/不能/没法/难以/拒绝/没有权限 + 提供/回答/获取/访问/查询/处理…
    re.compile(
        r"(?:无法|不能|没法|不可以|难以|拒绝|没有权限|不允许)"
        r"[^。!?！？]{0,8}(?:提供|回答|获取|访问|查询|处理|满足|做到|给出|告知|完成|执行|展示)"
    ),
    # 能力边界自述：作为(一个)AI/语言模型/助手…（允许逗号）
    re.compile(
        r"作为(?:一个|一名)?(?:AI|人工智能|语言模型|模型|助手|机器人)"
        r"[^。!?！？]{0,12}(?:无法|不能|没有|不|抱歉|只能)"
    ),
    # 直接道歉
    re.compile(r"(?:抱歉|对不起|不好意思|很遗憾|非常抱歉)"),
    # 无把握 / 答不上来
    re.compile(
        r"(?:不确定|不知道|不清楚|没把握|查不到|答不上|回答不了|"
        r"帮不了|帮不上|无法判断|无法确认|暂时无法)"
    ),
    # 需要外部条件才能回答
    re.compile(r"需要(?:联网|实时数据|最新信息|外部信息|更多信息)"),
    re.compile(r"没有(?:实时|最新|联网)数据"),
)


def _is_local_refusal(reply: str) -> bool:
    """本地答复是否为拒答/没把握（关键词快查 + 骨架正则兜底）。

    这类回复不能当正常答案交付：不落库、不展示，直接回退云端回答。
    """
    if not reply:
        return True
    if any(marker in reply for marker in _QA_FALLBACK_MARKERS):
        return True
    return any(pattern.search(reply) for pattern in _REFUSAL_PATTERNS)


# 列表题护栏：问题要求"有哪些/列举"，但本地只给了短答或没列表分隔符
# （如"欧盟国有哪些"→本地编"17个成员国"只报数没列）→ 判定没真列出来，
# 回退云端。常见类目枚举（猫科动物）本地能列 → 正常交付。
_LIST_REQUEST_MARKERS = ("有哪些", "哪些", "列举", "包括哪些", "有什么")
_LIST_ITEM_PUNCT = ("、", "，", ",", "和", "以及", "\n")


def _is_list_request(text: str) -> bool:
    return any(marker in text for marker in _LIST_REQUEST_MARKERS)


def _has_list_items(reply: str) -> bool:
    """回答里是否真的列了项（有列表分隔符，或足够长视为已展开）。"""
    if len(reply) >= 60:
        return True
    return any(punct in reply for punct in _LIST_ITEM_PUNCT)


# ---------------------------------------------------------------------------
# 指代补全：短指代后续（"分别是"/"然后呢"）拼上上一轮上下文。
# 历史/数据库保存原文，给模型的输入换成自包含补全版——解决多轮对话里
# "消息没发送完整"这类断点（云端 flash 对单独成句的指代后续理解弱）。
# ---------------------------------------------------------------------------

_REFERENTIAL_WORDS = (
    "分别是",
    "然后呢",
    "还有呢",
    "还有吗",
    "继续",
    "具体是",
    "都有哪些",
    "都是哪些",
    "是哪些",
    "具体有哪些",
    "然后",
    "还有",
    "那",
    "呢",
    "啥",
    "什么意思",
    "联网搜索",
    "搜索一下",
    "查一下",
)


def _expand_referential_followup(
    question: str, history: list[dict[str, Any]]
) -> str | None:
    """短指代后续 → 拼上上一轮上下文，返回自包含补全版；不命中返回 None。

    例："欧盟国有哪些"→答"27个成员国"→用户追问"分别是"：
    补全为"上一问：欧盟国有哪些。已回答：欧盟共有27个成员国。
    用户现在追问「分别是」…请结合上文理解并直接回答。"
    仅消息很短且命中指代词时生效；保存到历史的仍是用户原文。
    """
    q = str(question or "").strip()
    if not q or len(q) > 10:
        return None
    if not any(word in q for word in _REFERENTIAL_WORDS):
        return None
    prev_user = ""
    prev_ai = ""
    skipped_current = False
    for msg in reversed(history):
        role = msg.get("role")
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            if not skipped_current:
                # 最近一条 user 是刚保存的当前追问，跳过
                skipped_current = True
                continue
            if not prev_user:
                prev_user = content[:150]
        elif role == "assistant" and not prev_ai:
            prev_ai = content[:150]
        if prev_user and prev_ai:
            break
    if not prev_user:
        return None
    tail = f"已回答：{prev_ai}。" if prev_ai else ""
    return (
        f"上一问：{prev_user}。{tail}"
        f"用户现在追问「{q}」，这是承接上一问的后续问题，"
        f"请结合上文理解其含义并直接回答，不要反问。"
    )


def _replace_last_user(
    history: list[dict[str, Any]], new_content: str
) -> list[dict[str, Any]]:
    """返回把最近一条 user 消息内容替换为 new_content 的新历史（不改原列表）。"""
    result = list(history)
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "user":
            result[i] = {**result[i], "content": new_content}
            break
    return result


# ---------------------------------------------------------------------------
# 选项选择补全：用户点击选项卡片时，前端把 label 当普通消息发送（无标记），
# 模型常把"导出PDF报告"/"现代科技"当成新咨询/术语提问（各烧 23-28k token）。
# 这里在模型侧注入"（用户选择了选项 X，请按该选项执行）"，路由/历史仍原文。
# ---------------------------------------------------------------------------

_OPTIONS_BLOCK_RE = re.compile(r"```options\s*\n(.*?)```", re.S)


# 实时信息关键词：命中 → 系统层强制联网搜索（不依赖模型自觉）。
# 匹配时先去掉所有空白（"A 股" → "A股"），避免带空格漏网。
def _extract_choice_labels(content: str) -> list[str]:
    """从 AI 消息的 ```options 代码块提取选项 label。"""
    labels: list[str] = []
    for match in _OPTIONS_BLOCK_RE.finditer(content or ""):
        try:
            data = json.loads(match.group(1))
        except Exception:  # noqa: BLE001
            continue
        for opt in data.get("options", []):
            label = str(opt.get("label", "")).strip()
            if label:
                labels.append(label)
    return labels


def _expand_choice_selection(
    question: str, history: list[dict[str, Any]]
) -> str | None:
    """用户消息命中最近选项卡片的选项 label → 注入"选择了选项"上下文。

    例：上一问是"请选择PDF风格 [现代科技/通用现代/学术典雅]"，
    用户发"现代科技" → 补全为"（用户从上一问的选项卡片选择了「现代科技」，
    请按该选项执行，不要解释选项本身）"。
    仅匹配最近一条带 ```options 的 AI 消息；未命中返回 None。
    """
    q = str(question or "").strip()
    if not q:
        return None
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        labels = _extract_choice_labels(str(msg.get("content") or ""))
        if not labels:
            continue
        # 回传消息现为「【标题】label（副标题）」格式 → 用包含匹配
        # （最长 label 优先，防短 label 误吞），并保留消息原文让标题/副标题进入上下文
        matched = next(
            (
                label
                for label in sorted(labels, key=len, reverse=True)
                if label and label in q
            ),
            None,
        )
        if matched:
            return (
                f"（用户从上一问的选项卡片中选择了「{matched}」，"
                f"请按该选项执行，不要解释选项本身）用户消息原文：{q}"
            )
        break  # 最近一条带选项的消息未匹配 → 不再往前找
    return None


# 企业/产品知识类问题：1.5B 会自信地编造（如"英伟达自己没有大模型"——
# 实际有 Nemotron/Cosmos/GR00T 等）。命中知名公司名 → 不分流本地。
# 误伤方向安全：即便问题与公司无关（"苹果有什么营养"），最多多花一次
# 云端调用，也不会答错。
async def stream_local_chat(
    session_id: str,
    question: str,
    history: list[dict[str, Any]],
    locale: str | None,
    system_prompt: str | None = None,
    on_reply: Callable[[str], None] | None = None,
    defer_emit: bool = False,
) -> AsyncIterator[str]:
    """与本地模型直接对话：把最近会话发给 llama-server 流式回答。

    不走 agent（系统提示词 + 工具 schema 远超 0.5B 模型上下文），
    用精简系统提示词直连 llama.cpp 的 OpenAI 兼容接口。
    ``system_prompt`` 可传任务专用提示（本地能力路由）。

    传 ``on_reply`` 时：完整回答到手后回调它，由调用方决定是否落库/
    结束（用于"本地拒答 → 转云端"），本函数不再自动保存和发出 done 事件。
    ``defer_emit`` 为 True 时不边生成边发 message 事件（攒完整回复后
    一次性回调），避免本地拒答文本在转云端前闪现到气泡里。
    """
    from ..agent.core import get_manager

    manager = get_manager()
    if not manager.is_ready():
        yield error_event(
            "local_model_not_running",
            "本地模型未运行，请先在设置-意图中启动",
        )
        return

    from ..config import settings_store

    ctx_size = int(settings_store.load().get("local_llm_ctx_size") or 4096)
    messages = _build_local_chat_messages(
        question, history, locale, ctx_size, system_prompt
    )

    payload = {
        "model": "local",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": True,
    }
    parts: list[str] = []
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120, connect=5)
        ) as client:
            async with client.stream(
                "POST",
                f"http://127.0.0.1:{manager.port}/v1/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                        chunk = delta.get("content") or ""
                    except Exception:  # noqa: BLE001
                        continue
                    if chunk:
                        parts.append(chunk)
                        if not defer_emit:
                            yield sse_event("message", {"content": chunk})
    except Exception as exc:  # noqa: BLE001
        logger.warning("本地模型对话失败: %s", exc)
        yield error_event("local_chat_failed", f"本地模型对话失败: {exc}")
        return

    reply = "".join(parts).strip()
    if not reply:
        yield error_event("local_chat_empty", "本地模型没有返回内容")
        return
    if on_reply is not None:
        # 调用方接管：完整回答已流式展示，是否落库/结束由调用方决定
        on_reply(reply)
        return
    await asyncio.to_thread(
        db.add_message, session_id, "assistant", reply, source="local"
    )
    yield sse_event(
        "done",
        {
            "message": "回答完成",
            "messageKey": "tool.answerDone",
            "messageParams": {},
            "content": reply,
        },
    )
