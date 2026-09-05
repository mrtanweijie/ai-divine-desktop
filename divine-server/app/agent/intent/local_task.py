"""本地能力路由启发式（intent 侧收口，自 api/chat_local.py 迁入）。

服务「整轮对话是否交给本地模型直答」的分流判定：简单任务检测器
（translation/chat/extract/rewrite/calc/qa）、对应关键词表、实时信息
识别、AI 提问上下文提示（_ai_asking_hint）。

与同包 intent.py 的 classify_intents（工具裁剪/本地动作短路）是互补的
两层路由：二者关键词表语义不同（例如 _QUESTION_MARKERS 各有取舍——
qa 路由刻意不含「天气/几点」，避免 1.5B 幻觉实时信息），不可合并。
本地回答的护栏与生成（拒答识别/列表护栏/stream_local_chat）仍在
api/chat_local.py。
"""

from __future__ import annotations

import re
from typing import Any

_SMALL_LANGS = (
    "日语",
    "日文",
    "韩语",
    "韩文",
    "法语",
    "法文",
    "德语",
    "德文",
    "西班牙语",
    "俄语",
    "意大利语",
    "阿拉伯语",
    "葡萄牙语",
)


def _is_simple_translation(text: str) -> bool:
    """是否适合本地模型直答的简单翻译请求。

    条件：明确翻译意图（怎么翻译/翻译成/用英语/怎么说…）+ 目标语种是
    本地模型强项（英文/中文）+ 输入短。小语种（日/韩/法…）1.5B 会编造
    （实测"苹果→日语"编成 アイナップ），不分流走云端。
    """
    if not text or len(text) > 200:
        return False
    t = text.lower()
    has_translate = any(
        marker in t
        for marker in (
            "怎么翻译",
            "怎么翻",
            "翻译成",
            "翻译为",
            "翻译一下",
            "翻成",
            "怎么说",
            "怎么讲",
            "用英语",
            "用英文",
            "用中文",
            "用汉语",
            "英语怎么说",
            "英文怎么说",
            "中文怎么说",
            "英译中",
            "中译英",
            "translate",
            "英文意思",
            "中文意思",
            "英语意思",
            "翻译",  # 裸"翻译"：短内容（"吃什么 翻译"）→ 本地
        )
    )
    if not has_translate:
        return False
    # 文档/长文翻译 → 云端（1.5B 做不了整篇翻译）
    for doc_kw in (
        "文件",
        "文档",
        "pdf",
        "ppt",
        "word",
        "excel",
        "报告",
        "说明书",
        "整篇",
        "全文",
        "这份",
    ):
        if doc_kw in t:
            return False
    # 小语种 → 不本地分流（1.5B 训练数据少，容易一本正经地编造）
    for lang in _SMALL_LANGS:
        if lang in t:
            return False
    return True


# ---------------------------------------------------------------------------
# 本地能力路由：简单任务（翻译/闲聊/提取/改写/计算）本地模型直答，省 token。
# 每个任务 = 一个保守检测器 + 一个任务专用 system prompt；都带"答空回退云端"。
# ---------------------------------------------------------------------------

_LOCAL_TASK_PROMPTS: dict[str, str] = {
    "translation": (
        "你是翻译助手。针对用户的翻译问题给出准确、简洁的译文；"
        "若涉及多义词，可一句话点明语境差异。"
    ),
    "chat": "你是一个乐于助人的 AI 助手，请用中文简洁、准确地回答。",
    "extract": (
        "你是信息提取助手。把用户输入中的待办事项、日期、清单、"
        "关键信息提取为 JSON 输出，不要遗漏，不要编造原文没有的内容。"
    ),
    "rewrite": (
        "你是文字改写助手。按用户要求改写、润色、简化或修正错别字，"
        "保留原意，直接输出结果。"
    ),
    "calc": "你是计算助手。直接给出计算结果，简洁准确。",
    "qa": (
        "你是问答助手。如果确定答案，直接简洁回答（一两句话即可）；"
        "如果不确定、需要最新信息或可能编造，只输出「不确定」。"
    ),
}

_CHAT_MARKERS = (
    "你好",
    "您好",
    "谢谢",
    "感谢",
    "再见",
    "拜拜",
    "嗨",
    "哈喽",
    "早上好",
    "下午好",
    "晚上好",
    "在吗",
    "辛苦了",
    "hello",
    "hi",
    "thanks",
    "thank you",
    "bye",
    # 选项卡片常见回复（本地秒答，省云端 token）
    "暂时不用",
    "不用了",
    "不用",
    "好的",
    "好",
    "不需要",
    "算了",
    "没事",
    "不用谢谢",
    "先这样",
)
_EXTRACT_MARKERS = (
    "提取待办",
    "提取日程",
    "提取日期",
    "列出待办",
    "提取清单",
    "生成待办",
    "提取成json",
    "转成json",
    "提取信息",
    "总结待办",
)
_REWRITE_MARKERS = (
    "润色",
    "改写",
    "简化一下",
    "通顺",
    "错别字",
    "改一下",
    "更正式",
    "更口语",
    "扩写",
    "缩写",
)


# 整句匹配时剔除的首尾标点/空白（"谢谢！"、"好的。"这类短回复）
_CHAT_TRIM_CHARS = " \t\r\n，。！!？?、；;：:,.~～·—…“”‘’\"'（）()[]【】"


def _detect_simple_chat(text: str) -> bool:
    """问候/感谢/寒暄等简短闲聊 → 本地答（零风险省 token）。

    必须整句命中（剔除首尾标点）而非子串包含：标记里有「好」「不用」
    这类短词，子串匹配会把「这个方案挺好的」误判成闲聊，抢在
    rewrite/extract 等内容型检测器之前造成误分流。
    """
    if not text or len(text) > 30:
        return False
    t = text.lower().strip().strip(_CHAT_TRIM_CHARS)
    return t in _CHAT_MARKERS


def _detect_extract(text: str) -> bool:
    """结构化提取（待办/日程/日期/清单 → JSON）——1.5B 的强项。"""
    if not text or len(text) > 500:
        return False
    return any(marker in text.lower() for marker in _EXTRACT_MARKERS)


def _detect_rewrite(text: str) -> bool:
    """改写/润色/简化/修错别字——改写类 0 步推理，1.5B 稳。"""
    if not text or len(text) > 500:
        return False
    return any(marker in text for marker in _REWRITE_MARKERS)


def _detect_calc(text: str) -> bool:
    """简单算式（数字+运算符）——单步数学（GSM8K 77%）。"""
    if not text or len(text) > 50:
        return False
    import re

    return bool(re.search(r"\d+\s*[+\-*/×÷]\s*\d+", text))


_QUESTION_MARKERS = (
    "？",
    "?",
    "吗",
    "呢",
    "什么",
    "怎么",
    "哪",
    "谁",
    "为什么",
    "多少",
    "哪里",
    "几",
    "是不是",
    "是否",
    "哪个",
    "如何",
)
# 无标记短名词短语检测时排除的动作/命令词（避免把"帮我打开计算器"当问答）
_ACTION_WORDS = (
    "打开",
    "启动",
    "运行",
    "关闭",
    "退出",
    "截图",
    "截屏",
    "锁屏",
    "找文件",
    "搜索",
    "帮我",
    "请",
    "写",
    "生成",
    "制作",
    "翻译",
    "删除",
    "创建",
    "设置",
    "整理",
    "润色",
    "提取",
    "输出",
    "导出",
    "保存",
    "下载",
    "整理成",
    "转成",
    "做成",
    "生成一份",
)

# 文档/工具类词汇：出现即视为内容生成意图（本地模型无工具能力只会复读），
# 对 _detect_qa 的短名词兜底与问句兜底一并排除。大小写不敏感。
_DOC_TOOL_MARKERS = (
    "pdf",
    "word",
    "excel",
    "xlsx",
    "docx",
    "csv",
    "ppt",
    "幻灯",
    "演示文稿",
    "图表",
    "表格",
    "报告",
    "周报",
    "日报",
    "简历",
    "笔记",
    "文档",
    "思维导图",
    "图片",
)


# 精确数字类事实（1.5B 记不住会自信地编，如"南美洲有几个国家"→编 33）：
# 这类答案是一个精确数字，本地护栏（不确定）拦不住"自信的错"，回云端。
_NUMERIC_FACT_MARKERS = (
    "几个",
    "多少",
    "共有",
    "哪年",
    "多高",
    "多长",
    "多宽",
    "多久",
    "多大",
    "多少人口",
    "面积",
    "排名",
    "第几",
    "多少钱",
    "几点",
    "几岁",
    "多少位",
    "数量",
)


# 本地问答护栏回退信号：出现这些措辞 → 本地没把握/拒答 → 回退云端。
# 1.5B 被问实时数据时常用"无法提供/无法回答"式拒答，
# 而不是按提示词输出"不确定"，所以拒答话术也要算回退信号。
_QA_FALLBACK_MARKERS = (
    "不确定",
    "无法提供",
    "无法回答",
    "无法获取",
    "无法访问",
    "不能提供",
    "很抱歉",
    "抱歉",
)

# 拒答骨架正则：兜住关键词表漏网的措辞变体（"作为一个AI助手"、
# "我不能回答"、"回答不了"、"对不起"、"需要联网"…）。
# 方向性：误判为拒答只多花一次云端调用（安全方向）；漏判才会把
# "无法回答"当正常答案交付（原 bug），所以骨架宁宽勿窄。


_REALTIME_KEYWORDS = (
    "新闻",
    "天气",
    "股票",
    "股价",
    "行情",
    "最新",
    "实时",
    "热搜",
    "报价",
    "油价",
    "金价",
    "汇率",
    "今天有什么",
    "发生了什么",
    "今天热点",
    # 股市/行情类：1.5B 无实时数据，必拒 → 直接分流云端联网
    "A股",
    "股市",
    "大盘",
    "走势",
    "涨跌",
    "涨幅",
    "跌幅",
    "涨停",
    "跌停",
    "开盘",
    "收盘",
    "基金",
    "板块",
    "美股",
    "港股",
    "期货",
    "比特币",
)

# 结构性正则（关键词漏网的措辞变体，如"近一个月A股数据走势"、
# "茅台股价走势"、"上证指数今天收盘"）——时间区间/市场名词 + 行情动词的固定骨架。
_REALTIME_PATTERNS = (
    # 时间区间 + 数据/行情名词：近一个月/一周/30天 + 走势/行情/数据/表现/统计/点位/排名/价格
    re.compile(
        r"近.{0,3}?[月天周时年][^，。!?！？]{0,12}"
        r"(?:走势|行情|数据|表现|统计|点位|排名|价格|指数)"
    ),
    # 市场名词 + 行情动词/名词（含具体标的：上证指数收盘 / 美股今天走势）
    re.compile(
        r"(?:A股|a股|美股|港股|股市|大盘|上证|深证|沪深|创业板|科创板|"
        r"纳指|标普|道琼斯|恒生|日经|基金|板块|期货|原油|黄金|比特币|"
        r"金价|油价|汇率)\S{0,8}(?:走势|行情|指数|点位|股价|价格|数据|"
        r"表现|收盘|开盘|报收|涨跌|涨幅|跌幅)"
    ),
    # 具体个股/板块名 + 股 + 行情词（"茅台股价走势"、"芯片股跌了"）
    re.compile(r"\S{1,6}股(?:价)?\S{0,6}(?:走势|行情|数据|表现|今天|最新|涨|跌)"),
)


def _is_realtime_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if any(keyword in compact for keyword in _REALTIME_KEYWORDS):
        return True
    return any(pattern.search(compact) for pattern in _REALTIME_PATTERNS)


_ENTITY_KNOWLEDGE_MARKERS = (
    "英伟达",
    "苹果",
    "特斯拉",
    "华为",
    "小米",
    "三星",
    "谷歌",
    "微软",
    "亚马逊",
    "OpenAI",
    "百度",
    "腾讯",
    "阿里巴巴",
    "字节跳动",
    "比亚迪",
    "宁德时代",
    "英特尔",
    "高通",
    "台积电",
    "Meta",
    "IBM",
    "甲骨文",
    "任天堂",
)


def _detect_qa(text: str, ai_asking: bool = False) -> bool:
    """知识问答：常识/事实类问题本地直答（护栏式，不确定回退云端）。

    两类命中：
    - 带问句标记的短问题（≤60 字）；
    - 无标记的短名词短语（≤12 字，如"英国首都"）——排除动作/命令词，
      避免把"帮我打开计算器"这类本地动作误当问答。

    排除：
    - 小语种（编造风险）；
    - 精确数字事实（"几个/多少/哪年/人口"——1.5B 会自信地编）；
    - 企业/产品知识（"英伟达有什么大模型"——1.5B 会自信地编造）；
    - 文档/工具类词汇（PDF/Excel/报告…——这些是内容生成意图，本地模型
      无工具能力，只会复读原词，必须走云端）；
    - ai_asking=True（AI 上一条消息在等用户选择，短输入是省略式回答，
      需结合上下文理解 → 云端）。
    """
    if not text:
        return False
    t = text.strip()
    # AI 正在等用户选择/回答：短输入是省略式回答（如上轮问"要 PDF 吗？"，
    # 用户回"PDF"），绝不能当知识问答本地直答
    if ai_asking:
        return False
    # 文档/工具生成意图词：本地模型只会复读（实测"PDF"→回"PDF"），不分流
    lowered = t.lower()
    if any(marker in lowered for marker in _DOC_TOOL_MARKERS):
        return False
    # 实时信息请求（新闻/天气/股市行情…）→ 本地必拒答，不分流
    if _is_realtime_request(t):
        return False
    # 小语种翻译请求（"苹果 用日语怎么说"）→ 不分流（编造风险）
    if any(lang in t for lang in _SMALL_LANGS):
        return False
    # 精确数字事实 → 云端
    if any(marker in t for marker in _NUMERIC_FACT_MARKERS):
        return False
    # 企业/产品知识（公司产品线/发布动态 1.5B 会编）→ 云端
    if any(name in t for name in _ENTITY_KNOWLEDGE_MARKERS):
        return False
    if len(t) <= 60 and any(marker in t for marker in _QUESTION_MARKERS):
        return True
    if len(t) <= 12 and not any(word in t for word in _ACTION_WORDS):
        return True
    return False


_LOCAL_TASK_DETECTORS: tuple[tuple[str, Any], ...] = (
    ("translation", _is_simple_translation),
    ("chat", _detect_simple_chat),
    ("extract", _detect_extract),
    ("rewrite", _detect_rewrite),
    ("calc", _detect_calc),
    ("qa", _detect_qa),
)


def _detect_local_task(text: str, ai_asking: bool = False) -> str | None:
    """命中本地能力路由的任务名；未命中返回 None（走云端）。

    ai_asking=True 表示 AI 上一条消息正在等用户选择（省略式回答场景），
    此时禁用 qa 短名词兜底——省略式回答必须结合上下文理解，走云端。
    """
    for name, detect in _LOCAL_TASK_DETECTORS:
        if name == "qa" and ai_asking:
            continue
        if detect(text):
            return name
    return None


_AI_ASKING_MARKERS = (
    "还是",
    "或者",
    "需要我",
    "要不要",
    "想要哪种",
    "哪种",
    "请选择",
    "请告诉我",
    "选一个",
    "选一下",
    "补充",
    "吗",
)


def _ai_asking_hint(history: list[dict[str, Any]] | None) -> bool:
    """AI 是否在等用户选择/回答（省略式回答的信号）。

    history 末尾通常已包含当前这条用户输入（chat 保存先于路由），
    所以要跳过尾部连续的 user 消息，看它上面最近的 assistant 消息。
    """
    for message in reversed(history or []):
        if message.get("role") == "user":
            continue
        if message.get("role") == "assistant":
            tail = str(message.get("content") or "").strip()[-300:]
            if not tail:
                return False
            if tail.endswith(("？", "?")):
                return True
            return any(marker in tail for marker in _AI_ASKING_MARKERS)
        break
    return False
