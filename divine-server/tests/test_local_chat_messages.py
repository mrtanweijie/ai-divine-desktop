"""本地模型对话消息组装：按上下文预算裁剪历史，避免 400 exceed_context_size_error。

背景：history[-12:] 每条 2000 字符全塞会轻松超过 4096 ctx，llama.cpp
返回 400（request (N tokens) exceeds the available context size）。
"""

from __future__ import annotations


def _tokens(messages: list[dict[str, str]]) -> int:
    from app.agent.state import estimate_tokens

    return sum(estimate_tokens(m["content"]) for m in messages)


def test_long_history_trimmed_to_ctx():
    from app.api.chat import _build_local_chat_messages

    history = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"这是第{i}条很长的对话历史内容。" * 150,
        }
        for i in range(12)
    ]
    question = "帮我整理这份文档"
    messages = _build_local_chat_messages(question, history, "zh-CN", 4096)
    assert _tokens(messages) <= 4096
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": question}


def test_question_never_duplicated():
    from app.api.chat import _build_local_chat_messages

    question = "你好"
    history = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "回答一"},
        {"role": "user", "content": question},  # 刚保存的当前问题
    ]
    messages = _build_local_chat_messages(question, history, "zh-CN", 4096)
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    assert user_msgs == ["第一轮", question]


def test_short_history_all_kept():
    from app.api.chat import _build_local_chat_messages

    history = [
        {"role": "user", "content": "短"},
        {"role": "assistant", "content": "短答"},
    ]
    messages = _build_local_chat_messages("继续", history, "zh-CN", 4096)
    assert [m["content"] for m in messages] == [
        "你是一个乐于助人的 AI 助手，请用中文简洁、准确地回答。",
        "短",
        "短答",
        "继续",
    ]


def test_oversized_question_truncated():
    from app.api.chat import _build_local_chat_messages

    question = "很长的" * 500
    messages = _build_local_chat_messages(question, [], "zh-CN", 512)
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"]
    assert len(messages[-1]["content"]) < len(question)


def test_history_roles_filtered():
    from app.api.chat import _build_local_chat_messages

    history = [
        {"role": "user", "content": "问题"},
        {"role": "tool", "content": "工具结果不参与"},
        {"role": "assistant", "content": "回答"},
    ]
    messages = _build_local_chat_messages("下一个", history, "zh-CN", 4096)
    contents = [m["content"] for m in messages]
    assert "工具结果不参与" not in contents
    assert contents[-1] == "下一个"
