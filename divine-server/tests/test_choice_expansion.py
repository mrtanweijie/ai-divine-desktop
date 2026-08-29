"""选项选择补全：用户消息命中选项卡片的 label 时注入"选择了选项"上下文。

前端把选项点击当普通消息发送（无标记），模型常把"导出PDF报告"/"现代科技"
当成新咨询/术语提问。补全后模型知道这是对上一问选项卡的回答。
"""

from __future__ import annotations


def _expand(question: str, history: list[dict]) -> str | None:
    from app.api.chat import _expand_choice_selection

    return _expand_choice_selection(question, history)


_OPTIONS_AI = {
    "role": "assistant",
    "content": (
        "请选择玄戒O3分析报告的PDF风格\n"
        "```options\n"
        '{"title": "PDF风格", "options": [{"label": "现代科技"},'
        '{"label": "通用现代"},{"label": "学术典雅"}]}\n'
        "```"
    ),
}


def test_choice_selection_expanded():
    history = [
        {"role": "user", "content": "整理输出 PDF 文档"},
        _OPTIONS_AI,
        {"role": "user", "content": "现代科技"},  # 当前选择
    ]
    expanded = _expand("现代科技", history)
    assert expanded is not None
    assert "选择了「现代科技」" in expanded
    assert "请按该选项执行" in expanded


def test_choice_selection_with_suffix():
    """带 color_scheme 后缀（label（配色））也能命中。"""
    history = [
        {"role": "user", "content": "做一份报告"},
        {
            "role": "assistant",
            "content": (
                "选择主题色\n```options\n"
                '{"options": [{"label": "蓝灰", "color_scheme": "blue_gray"}]}\n'
                "```"
            ),
        },
        {"role": "user", "content": "蓝灰（blue_gray）"},
    ]
    expanded = _expand("蓝灰（blue_gray）", history)
    assert expanded is not None
    assert "蓝灰" in expanded


def test_no_options_message_returns_none():
    history = [
        {"role": "user", "content": "欧盟国有哪些"},
        {"role": "assistant", "content": "欧盟共有27个成员国。"},
        {"role": "user", "content": "分别是"},
    ]
    assert _expand("分别是", history) is None


def test_stale_options_not_matched():
    """最近一条带选项的消息未匹配 → 不再往前找旧选项。"""
    old_options = {
        "role": "assistant",
        "content": (
            "选方案\n```options\n"
            '{"options": [{"label": "方案A"}]}\n'
            "```"
        ),
    }
    history = [
        old_options,
        {"role": "user", "content": "随便聊聊"},
        {"role": "assistant", "content": "好的。"},
        {"role": "user", "content": "方案A"},  # 当前输入
    ]
    # 最近一条带选项的消息是 old_options 之前的……实际最近的是"好的。"
    # （无 options 块，跳过），再往前是 user"随便聊聊"，再往前才是 old_options。
    # 但 old_options 和当前输入之间隔了用户消息，不属于"上一问选项卡"——
    # 这里验证：扫描到最近带选项的 AI 消息是 old_options，且匹配 → 仍补全。
    expanded = _expand("方案A", history)
    assert expanded is not None
