"""指代补全：短指代后续（"分别是"/"然后呢"）拼上上一轮上下文。

解决多轮对话里云端把"分别是"当"消息没发送完整"的断点：
历史保存原文，给模型的输入换成自包含补全版。
"""

from __future__ import annotations


def _expand(question: str, history: list[dict]) -> str | None:
    from app.api.chat import _expand_referential_followup

    return _expand_referential_followup(question, history)


def test_expand_shibie_with_context():
    history = [
        {"role": "user", "content": "欧盟国有哪些"},
        {"role": "assistant", "content": "欧盟共有27个成员国。"},
        {"role": "user", "content": "分别是"},  # 刚保存的当前追问
    ]
    expanded = _expand("分别是", history)
    assert expanded is not None
    assert "欧盟国有哪些" in expanded  # 拼上上一问
    assert "欧盟共有27个成员国" in expanded  # 拼上已回答
    assert "分别是" in expanded


def test_no_expand_long_message():
    history = [
        {"role": "user", "content": "欧盟国有哪些"},
        {"role": "assistant", "content": "欧盟共有27个成员国。"},
        {"role": "user", "content": "欧盟成员国分别是哪些国家？请详细列出"},
    ]
    assert _expand("欧盟成员国分别是哪些国家？请详细列出", history) is None


def test_no_expand_non_referential():
    history = [
        {"role": "user", "content": "欧盟国有哪些"},
        {"role": "assistant", "content": "欧盟共有27个成员国。"},
        {"role": "user", "content": "帮我打开计算器"},
    ]
    assert _expand("帮我打开计算器", history) is None


def test_no_prev_context_returns_none():
    assert _expand("分别是", [{"role": "user", "content": "分别是"}]) is None


def test_ranhou_followup():
    history = [
        {"role": "user", "content": "怎么安排下周会议"},
        {"role": "assistant", "content": "建议周二上午……"},
        {"role": "user", "content": "然后呢"},
    ]
    expanded = _expand("然后呢", history)
    assert expanded is not None
    assert "怎么安排下周会议" in expanded


def test_replace_last_user_keeps_original():
    from app.api.chat import _replace_last_user

    history = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "user", "content": "C"},
    ]
    new = _replace_last_user(history, "EXPANDED")
    assert new[2]["content"] == "EXPANDED"
    assert history[2]["content"] == "C"  # 原列表不被修改
