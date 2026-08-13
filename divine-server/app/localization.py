from __future__ import annotations

from typing import Any

SUPPORTED_LOCALES = {"zh-CN", "zh-TW", "en"}
DEFAULT_LOCALE = "zh-CN"


def normalize_locale(value: str | None) -> str:
    locale = (value or "").strip()
    normalized = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hant": "zh-TW",
        "zh-hk": "zh-TW",
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
    }.get(locale.lower())
    return normalized if normalized in SUPPORTED_LOCALES else DEFAULT_LOCALE


def language_instruction(locale: str) -> str:
    normalized = normalize_locale(locale)
    if normalized == "en":
        return (
            "Always reply in English. Keep user-facing text, chart labels, "
            "Mermaid labels, HTML/PPT copy, and exported document titles in "
            "English. Keep code, paths, commands, and raw tool output unchanged."
        )
    if normalized == "zh-TW":
        return (
            "請始終使用繁體中文回覆用戶。用戶可見正文、圖表標題與標籤、"
            "Mermaid 文字、HTML/PPT 文案、匯出文件標題都應使用繁體中文；"
            "程式碼、路徑、指令、終端輸出保持原文。"
        )
    return (
        "请始终使用简体中文回复用户。用户可见正文、图表标题与标签、"
        "Mermaid 文本、HTML/PPT 文案、导出文档标题都应使用简体中文；"
        "代码、路径、命令、终端输出保持原文。"
    )


def http_accept_language(locale: str) -> str:
    normalized = normalize_locale(locale)
    return {
        "zh-CN": "zh-CN,zh;q=0.9",
        "zh-TW": "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
        "en": "en-US,en;q=0.9",
    }[normalized]


def export_labels(locale: str) -> dict[str, str]:
    normalized = normalize_locale(locale)
    return {
        "zh-CN": {
            "title": "对话导出",
            "exported_at": "导出时间",
            "user": "用户",
            "ai": "AI",
        },
        "zh-TW": {
            "title": "對話匯出",
            "exported_at": "匯出時間",
            "user": "使用者",
            "ai": "AI",
        },
        "en": {
            "title": "Chat Export",
            "exported_at": "Exported at",
            "user": "User",
            "ai": "AI",
        },
    }[normalized]


def default_session_title(locale: str) -> str:
    normalized = normalize_locale(locale)
    return {
        "zh-CN": "新对话",
        "zh-TW": "新對話",
        "en": "New Chat",
    }[normalized]


def localized_message(
    key: str,
    params: dict[str, Any] | None = None,
    fallback: str = "",
) -> dict[str, Any]:
    return {
        "messageKey": key,
        "messageParams": params or {},
        "message": fallback,
    }
