"""本地聊天子系统：简单任务本地模型直答 + 启发式分流。

从 api/chat.py 拆分而来（原 715-1616 行）：路由层（stream_chat / retry_cloud）
留在 chat.py，这里收拢「本地能力路由」的全部逻辑——
简单任务检测器、指代/选项补全、实时信息识别、本地拒答护栏、
本地模型直答（流式/非流式）。

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


def _detect_simple_chat(text: str) -> bool:
    """问候/感谢/寒暄等简短闲聊 → 本地答（零风险省 token）。"""
    if not text or len(text) > 30:
        return False
    t = text.lower().strip()
    return any(marker in t for marker in _CHAT_MARKERS)


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
