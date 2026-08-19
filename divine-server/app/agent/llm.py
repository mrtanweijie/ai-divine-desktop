"""Provider selection shared by agent runs."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings_store
from ..localization import normalize_locale
from ..llm import ChatDeepSeekProvider, MockChatModel, OpenAIChatProvider

logger = logging.getLogger("divine.agent.llm")

def _compact_cjk_spaces(text: str) -> str:
    return re.sub(
        r"(?<=[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff])"
        r"[\s\u3000]+"
        r"(?=[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff])",
        "",
        text,
    )

def _resolve_model_entry(
    settings: dict[str, Any], model_id: str | None
) -> dict[str, Any]:
    """Pick the model entry for this run: explicit per-message model_id wins,
    otherwise the settings-active (default) model, otherwise the first entry."""
    models = settings.get("models") or []
    if model_id:
        for entry in models:
            if isinstance(entry, dict) and entry.get("id") == model_id:
                return entry
    for entry in models:
        if isinstance(entry, dict) and entry.get("active"):
            return entry
    if models and isinstance(models[0], dict):
        return models[0]
    return {
        "provider": settings.get("provider", "auto"),
        "model": settings.get("model") or "deepseek-v4-flash",
        "base_url": settings.get("base_url", ""),
        "api_key": settings.get("api_key", ""),
    }

def _is_deepseek_endpoint(base_url: str) -> bool:
    """Check if the base_url points to a DeepSeek endpoint."""
    return "deepseek" in base_url.lower()


def _build_llm(
    think: bool = False,
    effort: str | None = None,
    model_id: str | None = None,
) -> Any:
    settings = settings_store.load()
    entry = _resolve_model_entry(settings, model_id)
    provider = entry.get("provider") or "auto"
    if provider == "mock":
        return MockChatModel()
    if provider == "auto" and not entry.get("api_key"):
        return MockChatModel()
    base_url = str(entry.get("base_url") or "").strip()
    # DeepSeek 端点 → ChatDeepSeekProvider（支持 thinking 扩展）
    # 其它 OpenAI 兼容端点（mimo 等） → OpenAIChatProvider（纯 ChatOpenAI）
    if _is_deepseek_endpoint(base_url):
        return ChatDeepSeekProvider(think=think, effort=effort, entry=entry).llm
    return OpenAIChatProvider(entry=entry).llm

async def generate_session_title(
    llm: Any,
    question: str,
    answer: str,
    locale: str,
) -> str:
    """Summarize a new conversation into a short, localized session title."""
    language = {
        "zh-CN": "简体中文",
        "zh-TW": "繁體中文",
        "en": "English",
    }.get(normalize_locale(locale), "简体中文")
    system = (
        "你是对话标题总结助手。请根据用户问题和 AI 回答，"
        f"用{language}生成一个简洁的会话标题，不超过 20 字。"
        "只输出标题本身，不要引号、标点、编号或解释。"
        "英文单词要连续输出，不要拆分成片段；中文标题内不要用空格分词。"
    )
    prompt = (
        f"用户问题：{(question or '').strip()[:300]}\n\n"
        f"AI 回答：{(answer or '').strip()[:1200]}"
    )
    try:
        text_parts: list[str] = []
        async with asyncio.timeout(10):
            async for chunk in llm.astream(
                [SystemMessage(content=system), HumanMessage(content=prompt)]
            ):
                content = chunk.content
                if isinstance(content, list):
                    content = "".join(
                        str(part.get("text") or "")
                        for part in content
                        if isinstance(part, dict)
                    )
                text = str(content or "")
                if text.strip():
                    text_parts.append(text)
        title = "".join(text_parts).strip().strip("\"'“”「」『』")
        if normalize_locale(locale) == "en":
            return " ".join(title.split())[:30]
        title = re.sub(r"\s+", " ", title)
        return _compact_cjk_spaces(title)[:30]
    except Exception as exc:  # noqa: BLE001
        logger.warning("session title generation failed: %s", exc)
        return ""
