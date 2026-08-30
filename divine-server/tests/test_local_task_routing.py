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


def test_weather_question_not_local():
    """天气需实时信息 → 系统层强制联网分流，不再命中本地 qa。"""
    assert _task("今天天气怎么样") is None


def test_market_query_not_local():
    """股市/行情请求（1.5B 无实时数据必拒答）→ 不分流，走云端联网。"""
    assert _task("近一个月 A 股数据走势") is None
    assert _task("今天的大盘怎么样") is None
    assert _task("茅台股价走势") is None
    assert _task("帮我看看最近美股行情") is None
    # 正则兜住的措辞变体（关键词表里没有的词）
    assert _task("上证指数今天收盘点位") is None
    assert _task("近一周基金收益排名") is None
    assert _task("芯片股今天涨了") is None


def test_realtime_detection():
    """实时信息关键词：空格归一（"A 股"→"A股"），新闻/天气/股市全覆盖。"""
    from app.api.chat import _is_realtime_request

    assert _is_realtime_request("近一个月 A 股数据走势") is True
    assert _is_realtime_request("A股今日大盘") is True
    assert _is_realtime_request("今天天气怎么样") is True
    assert _is_realtime_request("最新科技新闻") is True
    assert _is_realtime_request("上证指数今天收盘点位") is True
    assert _is_realtime_request("茅台股价走势") is True
    # 非实时内容不误伤
    assert _is_realtime_request("英国首都") is False
    assert _is_realtime_request("帮我整理会议纪要") is False
    assert _is_realtime_request("股东会决议需要全体签字") is False
    assert _is_realtime_request("今天心情不错，谢谢") is False


def test_qa_refusal_is_fallback_signal():
    """本地拒答话术（"无法提供实时数据"）要算回退信号，不能当正常回答返回。"""
    from app.api.chat import _is_local_refusal

    # 关键词表直接命中
    refusal = "作为 AI，我无法提供实时数据或最新信息。建议您查看最新的财经新闻。"
    assert _is_local_refusal(refusal) is True
    # 骨架正则兜住的变体（关键词表没有的词/隔字）
    assert _is_local_refusal("作为一个AI助手，我不能回答这个问题。") is True
    assert _is_local_refusal("对不起，我无法帮您查询实时数据。") is True
    assert _is_local_refusal("这个问题我回答不了。") is True
    assert _is_local_refusal("我暂时无法获取相关信息。") is True
    assert _is_local_refusal("需要联网才能查到最新数据。") is True
    assert _is_local_refusal("我不确定，这个问题需要查证。") is True
    # 正常回答不受影响
    assert _is_local_refusal("英国首都是伦敦。") is False
    assert _is_local_refusal("太阳从东方升起。") is False
    assert _is_local_refusal("这个公式不能直接套用，需要先化简。") is False
    assert _is_local_refusal("作为AI，我可以帮你翻译这句话。") is False
    assert _is_local_refusal("谢谢你，再见。") is False


def test_list_guard():
    """列表题护栏：要列表但本地只给短答/没列 → 回退云端。"""
    from app.api.chat import _has_list_items, _is_list_request

    assert _is_list_request("欧盟国有哪些") is True
    assert _is_list_request("猫科有哪些常见动物") is True
    assert _is_list_request("英伟达有什么大模型") is True
    assert _is_list_request("英国首都") is False

    # "欧盟国有17个成员国。"（无列表分隔符，短）→ 判定没列 → 回退
    assert _has_list_items("欧盟国有17个成员国。") is False
    # "狮子、老虎、豹猫…"（有顿号）→ 判定列了 → 本地交付
    assert _has_list_items("包括狮子、老虎、美洲豹、雪豹、豹猫等。") is True
    # 长回答视为已展开
    assert _has_list_items("欧盟共有27个成员国，分别是德国、法国、意大利、" + "内容" * 30) is True


def test_entity_knowledge_falls_back():
    """企业/产品知识（1.5B 会自信编造，如"英伟达自己没有大模型"）→ 云端。"""
    assert _task("英伟达自己有什么大模型") is None
    assert _task("华为最新发布了什么手机") is None
    assert _task("特斯拉有哪些车型") is None
    assert _task("苹果公司什么时候成立的") is None
    # 误伤方向安全：含公司名的普通问题也走云端（宁可多花 token 不答错）
    assert _task("苹果有什么营养") is None


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


def test_pdf_short_tool_word_not_local():
    """文档/工具词（PDF 等）是内容生成意图：本地模型只会复读，必须走云端。

    原缺陷：『PDF』命中 qa 短名词兜底 → 1.5B 本地模型复读"PDF"，
    用户不得不重新输入完整指令才走云端。
    """
    assert _task("PDF") is None
    assert _task("输出 PDF 报告") is None
    assert _task("导出 excel") is None
    assert _task("帮我写周报") is None


def test_short_answer_after_ai_question_not_local():
    """AI 正在等用户选择时，短输入是省略式回答 → 必须结合上下文，走云端。"""
    from app.api.chat import _ai_asking_hint, _detect_local_task

    history = [
        {"role": "user", "content": "分析计费数据"},
        {
            "role": "assistant",
            "content": "需要我把这份分析整理成一份 Markdown 笔记 / Excel 表格 / "
            "PDF 报告，或补充「百炼对应字段」的映射吗？",
        },
        {"role": "user", "content": "PDF"},
    ]
    assert _ai_asking_hint(history) is True
    assert _detect_local_task("PDF", _ai_asking_hint(history)) is None
    # 带问号的正常提问在 AI 提问后同样回云端（省略式回答方向性优先）
    assert _detect_local_task("哪个更划算？", _ai_asking_hint(history)) is None


def test_ai_asking_hint_scoping():
    from app.api.chat import _ai_asking_hint

    # 最后一条是 assistant 且带"吗" → True
    assert _ai_asking_hint([{"role": "assistant", "content": "要继续吗？"}]) is True
    # 最后一条是 assistant 的普通陈述（无提问语气）→ False
    assert (
        _ai_asking_hint([{"role": "assistant", "content": "已生成周报。"}]) is False
    )
    # 尾部 user 消息是当前输入（chat 先保存后路由）：跳过它看上面的
    # assistant——"要继续吗？"之后用户回"要"正是省略式回答 → True
    assert (
        _ai_asking_hint(
            [{"role": "assistant", "content": "要继续吗？"}, {"role": "user", "content": "要"}]
        )
        is True
    )
    # 空历史 → False
    assert _ai_asking_hint([]) is False


def test_noun_qa_still_routed():
    """原有短名词问答能力不受文档词排除影响。"""
    assert _task("英国首都") == "qa"
