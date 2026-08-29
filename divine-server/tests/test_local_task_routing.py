"""本地能力路由：_detect_local_task 对五类简单任务的分发与兜底。

翻译 / 闲聊 / 提取 / 改写 / 计算 → 本地模型直答省 token；
未命中（复杂任务/事实问答）→ 走云端。
"""

from __future__ import annotations


def _task(text: str) -> str | None:
    from app.api.chat import _detect_local_task

    return _detect_local_task(text)


def test_translation_routed():
    assert _task('"简单" 英文怎么翻译') == "translation"
    assert _task("你好 用英语怎么说") == "translation"


def test_small_language_falls_back():
    # 小语种 1.5B 会编造 → 不分流
    assert _task("苹果 用日语怎么说") is None


def test_simple_chat_routed():
    assert _task("你好") == "chat"
    assert _task("谢谢！") == "chat"
    assert _task("再见") == "chat"
    assert _task("hello") == "chat"


def test_extract_routed():
    assert _task("从这段会议纪要提取待办事项：明天开会，周五交报告") == "extract"
    assert _task("把下面的日程提取成json：周一 10 点评审") == "extract"


def test_rewrite_routed():
    assert _task("帮我润色这句话：这个方案挺好的") == "rewrite"
    assert _task("改一下这段的错别字") == "rewrite"
    assert _task("简化一下这段文字") == "rewrite"


def test_calc_routed():
    assert _task("123+456=？") == "calc"
    assert _task("3.5×2 等于多少") == "calc"


def test_complex_tasks_fall_back():
    assert _task("帮我打开计算器") is None
    assert _task("请写一篇关于人工智能的文章") is None
    assert _task("帮我整理这段会议纪要") is None


def test_qa_routed():
    """常识/事实问答 → 本地（护栏式，不确定回退云端）。"""
    assert _task("英国首都") == "qa"
    assert _task("法国首都是哪") == "qa"
    assert _task("太阳从哪边升起") == "qa"
    assert _task("伦敦在哪") == "qa"


def test_weather_question_is_qa_then_falls_back():
    """天气这类需实时信息的问题命中 qa，但本地会答'不确定'回退云端。"""
    assert _task("今天天气怎么样") == "qa"


def test_list_guard():
    """列表题护栏：要列表但本地只给短答/没列 → 回退云端。"""
    from app.api.chat import _has_list_items, _is_list_request

    assert _is_list_request("欧盟国有哪些") is True
    assert _is_list_request("猫科有哪些常见动物") is True
    assert _is_list_request("英国首都") is False

    # "欧盟国有17个成员国。"（无列表分隔符，短）→ 判定没列 → 回退
    assert _has_list_items("欧盟国有17个成员国。") is False
    # "狮子、老虎、豹猫…"（有顿号）→ 判定列了 → 本地交付
    assert _has_list_items("包括狮子、老虎、美洲豹、雪豹、豹猫等。") is True
    # 长回答视为已展开
    assert _has_list_items("欧盟共有27个成员国，分别是德国、法国、意大利、" + "内容" * 30) is True


def test_numeric_facts_fall_back():
    """精确数字事实（1.5B 会自信地编）→ 不分流回云端。"""
    assert _task("南美洲有几个国家，分别是什么") is None
    assert _task("广西有哪几个市") is None
    assert _task("中国人口多少") is None
    assert _task("珠穆朗玛峰多高") is None


def test_command_not_misrouted_as_qa():
    """动作/命令类短句不被当问答（避免本地误答命令）。"""
    assert _task("帮我打开计算器") is None
    assert _task("关闭浏览器") is None
    assert _task("帮我找文件") is None


def test_long_input_falls_back():
    long_text = "帮我润色这段话：" + "内容" * 600
    assert _task(long_text) is None
