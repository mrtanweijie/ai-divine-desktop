"""Workspace RAG context assembly for agent prompts."""

from __future__ import annotations

from typing import Any

from ..rag_store import (
    index_workspace as rag_index_workspace,
    search_workspace as rag_search_workspace,
)

_RAG_KEYWORDS = (
    "笔记",
    "文件",
    "文档",
    "目录",
    "资料",
    "章节",
    "大纲",
    "小说",
    "续写",
    "内容",
    "方案",
    "工作区",
    "里面",
    "之前",
)

def _auto_rag_context(
    history: list[dict[str, Any]], workspace: Any
) -> str | None:
    question = next(
        (
            message.get("content", "")
            for message in reversed(history)
            if message.get("role") == "user"
        ),
        "",
    )
    question = (question or "").strip()
    if not question:
        return None
    try:
        results = rag_search_workspace(workspace, question, 3)
        if not results and any(
            keyword in question for keyword in _RAG_KEYWORDS
        ):
            rag_index_workspace(workspace)
            results = rag_search_workspace(workspace, question, 3)
    except Exception:
        return None
    if not results:
        return None
    blocks = [
        f"[{result['file_path']}]\n{result['snippet']}"
        for result in results
    ]
    return (
        "以下是工作区本地资料检索结果：\n\n"
        + "\n\n".join(blocks)
        + "\n\n请优先结合这些资料回答用户问题。"
    )
