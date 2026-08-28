"""Intent classification for selective system-prompt section injection.

The full ``SYSTEM_PROMPT`` (~8k tokens) is only needed when the matching
capability is actually in play. Each turn we classify the user's latest
message plus a small AI-side context tail into intent labels, then assemble
only the always-on core sections plus the sections for the active intents.

Intent labels are produced by pure local keyword matching (no LLM call);
tool-run history backfills intents for short follow-ups like "换个颜色".
"""

from __future__ import annotations

import re
from typing import Any

from .. import db
from .constants import SYSTEM_PROMPT
from .prompt_sections import (
    _CHART_RULES,
    _DATA_TOOL_RULES,
    _DOCUMENT_RULES,
    _FILE_AND_WEB_RULES,
    _FILE_SEARCH_RULES,
    _GENERAL_RULES,
    _IMAGE_GENERATION_RULES,
    _MEMORY_RULES,
    _MERMAID_RULES,
    _OPTIONS_CARD_MINI_RULES,
    _OPTIONS_CARD_RULES,
    _PDF_RENDER_RULES,
    _PDF_STYLE_RULES,
    _PDF_TRAVEL_RULES,
    _PROJECT_WORKFLOW,
    _RESUME_RULES,
    _SKILL_RULES,
    _SUBAGENT_RULES,
    _SVG_RULES,
    _TERMINAL_RULES,
    _UX_HTML_RULES,
)

# ---------------------------------------------------------------------------
# Section grouping
# ---------------------------------------------------------------------------

# 始终注入的核心行为规则（~1.5k tokens）：对话、文件读写、卡片基础、数据工具、网页抓取
ALWAYS_SECTIONS: tuple[str, ...] = (
    _GENERAL_RULES,
    _FILE_SEARCH_RULES,
    _OPTIONS_CARD_MINI_RULES,  # 精简版：只保留“何时弹卡片 + 基本格式”
    _DATA_TOOL_RULES,
    _FILE_AND_WEB_RULES,
)

# 条件注入：意图标签 -> 相关规则节
CONDITIONAL_SECTIONS: dict[str, tuple[str, ...]] = {
    "pdf": (_PDF_STYLE_RULES, _PDF_TRAVEL_RULES, _PDF_RENDER_RULES),
    "resume": (_RESUME_RULES,),
    "document": (_DOCUMENT_RULES,),
    "image": (_IMAGE_GENERATION_RULES,),
    "svg": (_SVG_RULES,),
    "chart": (_CHART_RULES,),
    "mermaid": (_MERMAID_RULES,),
    "ux": (_UX_HTML_RULES,),
    "skill": (_SKILL_RULES,),
    "terminal": (_TERMINAL_RULES,),
    "subagent": (_SUBAGENT_RULES,),
    "project": (_PROJECT_WORKFLOW,),
    "memory": (_MEMORY_RULES,),
}

# 条件节输出顺序（对齐旧版 SYSTEM_PROMPT 中规则块的原始顺序，保持输出稳定）
_INTENT_ORDER: tuple[str, ...] = (
    "skill",
    "image",
    "pdf",
    "document",
    "resume",
    "mermaid",
    "svg",
    "ux",
    "chart",
    "terminal",
    "subagent",
    "project",
    "memory",
)

# ---------------------------------------------------------------------------
# Keyword table
# ---------------------------------------------------------------------------

# 关键词一律小写；匹配时对文本做 .lower()（中文不受影响）。
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # 桌面操作（高频，优先匹配）
    "open_app": (
        "打开",
        "启动",
        "运行",
        "open",
        "launch",
        "start",
    ),
    "screenshot": (
        "截屏",
        "截图",
        "抓屏",
        "截取屏幕",
        "screenshot",
        "screen capture",
    ),
    "lock_screen": (
        "锁屏",
        "锁定",
        "lock screen",
        "lock",
    ),
    "search_file": (
        "找文件",
        "搜索文件",
        "查找文件",
        "find file",
        "search file",
    ),
    # PDF 相关（旅行手册 / 攻略 / 封面 / 风格 / 配色）
    "pdf": (
        "pdf",
        "旅行手册",
        "旅行攻略",
        "行程手册",
        "路线手册",
        "风格表",
        "封面",
        "配图",
        "主题色",
        "生成手册",
        "攻略",
        "行程单",
    ),
    # 简历
    "resume": (
        "简历",
        "resume",
        "求职",
        "工作经历",
        "目标岗位",
        "boss直聘",
        "linkedin",
    ),
    # Word / PPT
    "document": (
        "word",
        "ppt",
        "演示文稿",
        "幻灯片",
        "word_document",
        "生成word",
        "生成ppt",
    ),
    # 图片生成
    "image": (
        "生成图片",
        "文生图",
        "图生图",
        "图片生成",
        "image_generate",
        "插画",
        "画图",
        "画一张",
        "画一幅",
        "海报",
    ),
    # SVG 矢量图
    "svg": ("svg", "矢量图", "draw_svg", "edit_svg", "矢量"),
    # 数据图表
    "chart": (
        "图表",
        "chart",
        "趋势图",
        "柱状图",
        "饼图",
        "echarts",
        "generate_chart",
        "折线图",
        "散点图",
    ),
    # Mermaid 流程图
    "mermaid": ("流程图", "时序图", "架构图", "mermaid", "甘特图"),
    # UX 交互原型
    "ux": (
        "ux原型",
        "交互原型",
        "产品界面",
        "ux_html",
        "notion风格",
        "linear风格",
        "apple风格",
        "可点击演示",
    ),
    # 技能迁移 / 安装
    "skill": (
        "技能",
        "skill",
        "迁移",
        "claude code",
        "qoder",
        "cursor",
        "install_skill",
        "migrate",
        "导入技能",
        "安装技能",
    ),
    # 终端
    "terminal": ("终端", "terminal", "命令行", "执行命令", "shell", "运行命令"),
    # 并行子 Agent
    "subagent": (
        "子agent",
        "subagent",
        "并行",
        "run_subagents",
        "同时调研",
        "多来源",
    ),
    # 记忆
    "memory": (
        "记住",
        "忘掉",
        "忘记",
        "记得",
        "remember",
        "forget",
        "偏好",
        "习惯",
    ),
}

# project 意图两级关键词：强关键词命中一个即触发；
# 弱关键词需命中 >= 2 个才触发（避免“这段代码什么意思”这类提问误触发）。
_PROJECT_STRONG_KEYWORDS: tuple[str, ...] = (
    "开发",
    "重构",
    "调试",
    "修复",
    "bug",
    "commit",
    "部署",
    "编译",
    "运行测试",
    "写代码",
    "实现功能",
    "创建项目",
    "搭建",
    "脚手架",
    "报错",
    "异常",
    "排查",
    "依赖",
    "接口对接",
    "前端",
    "后端",
    "数据库设计",
    "写一个函数",
    "写个函数",
    "修复问题",
)
_PROJECT_WEAK_KEYWORDS: tuple[str, ...] = (
    "代码",
    "项目",
    "git",
    "模块",
    "函数",
    "组件",
    "配置",
    "文件结构",
    "页面",
)

# 工具调用 -> 意图标签（用于后续短指令“换个颜色”“继续”的意图回补）
_TOOL_TO_INTENT: dict[str, str] = {
    "pdf_generate": "pdf",
    "pdf_render": "pdf",
    "word_document": "document",
    "presentation": "document",
    "image_generate": "image",
    "draw_svg": "svg",
    "edit_svg": "svg",
    "generate_chart": "chart",
    "mermaid_export": "mermaid",
    "ux_html": "ux",
    "terminal": "terminal",
    "run_subagents": "subagent",
    "migrate_skill": "skill",
    "migrate_skills": "skill",
    "install_skill": "skill",
    "remember": "memory",
    "forget_memory": "memory",
    # 编码类工具：只要模型开始写代码/查代码，就补注项目工作流，
    # 不再依赖用户消息里的关键词命中（“帮我改下这个函数”也能触发）。
    "edit_files": "project",
    "write_file": "project",
    "git_status": "project",
    "git_diff": "project",
    "git_log": "project",
}

# 上下文不可贡献的意图：本地动作类必须由用户当前消息明确触发。
# 上一条 AI 回复里的动作词（如"已截图保存到 …/screenshot-xxx.png"）会
# 污染关键词分类，导致后续消息被误判成截图并误执行本地动作。
_CONTEXT_EXCLUDED_INTENTS = {"open_app", "screenshot", "lock_screen", "search_file"}

# 绝对路径（含空格/中文，带扩展名或纯目录）：用户直接发路径时，路径内部的
# 动作词（如 screenshots/截图）不应触发本地动作——纯路径消息应交给云端
# 读取文件（read_file/read_image），而不是误执行截图等本地动作。
_ABS_PATH_RE = re.compile(
    r"(?<!\w)(?:(?:/|~/|(?:[A-Za-z]:[\\/]))[^\n，。；、！？\"'`<>|*?#\[\]]{3,}\.\w{1,5}"
    r"|(?:/|~/|(?:[A-Za-z]:[\\/]))[\w\-./\\（）()%+@,'_\u4e00-\u9fff]{3,}[\w)\u4e00-\u9fff])"
)


def classify_intents(
    text: str,
    history_context: str = "",
    local_llm_enabled: bool = False,
    local_llm_mode: str = "keyword",  # "keyword" | "local" | "hybrid"
    local_llm_threshold: float = 0.75,
) -> tuple[set[str], dict[str, Any] | None]:
    """从用户消息（+ 上一条 AI 回复上下文）中提取意图标签集合。

    上下文参与所有消息的关键词匹配（"换个颜色"→ pdf、"继续"→ 上次任务），
    但本地动作类意图（open_app/screenshot/lock_screen/search_file）只能来自
    用户当前消息——上一条回复里的动作词会污染分类、误触发本地动作。
    本地模型只分类用户当前消息（其类别里也没有 pdf 等文档类目）。

    返回: (intents, local_result)
        - intents: 意图标签集合
        - local_result: 本地模型分类结果（如有），否则 None

    模式语义：
        - keyword: 仅关键词匹配，不调本地模型
        - local/hybrid: 始终调用本地模型，本地意图与关键词意图取并集
          （hybrid 的"关键词 + AI 双重判断"即两者都参与）
    """
    # 去掉消息里的绝对路径再判断意图：路径内部的动作词（screenshots/截图）
    # 不应触发本地动作；纯路径消息交给云端读取文件
    intent_text = _ABS_PATH_RE.sub(" ", text)
    combined = intent_text.lower()
    intents: set[str] = set()

    # Step 1: 关键词匹配 —— 当前消息全部意图都算
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            intents.add(intent)

    # 上下文只补充非本地动作类意图，避免动作词污染
    if history_context:
        ctx = history_context.lower()
        for intent, keywords in _INTENT_KEYWORDS.items():
            if intent in _CONTEXT_EXCLUDED_INTENTS:
                continue
            if any(keyword in ctx for keyword in keywords):
                intents.add(intent)

    # project 精度：强 >=1 或 弱 >=2（只按当前消息，不按上下文）
    strong_hits = sum(
        1 for keyword in _PROJECT_STRONG_KEYWORDS if keyword in combined
    )
    weak_hits = sum(
        1 for keyword in _PROJECT_WEAK_KEYWORDS if keyword in combined
    )
    if strong_hits >= 1 or weak_hits >= 2:
        intents.add("project")

    # Step 2: 本地模型分类（可选，只看用户当前消息）
    local_result = None
    if local_llm_enabled:
        # local / hybrid 都始终调用本地模型（"双重判断"）；keyword 模式不调。
        # 本地意图与关键词意图取并集，_can_handle_locally 再决定是否短路本地。
        try:
            from .local_llm import get_manager

            manager = get_manager()
            if manager.is_ready():
                # 本地模型也只看去掉路径后的文本；纯路径消息直接交给云端
                local_input = intent_text.strip()
                local_result = (
                    manager.classify(local_input) if local_input else None
                )
                if local_result and local_result["confidence"] >= local_llm_threshold:
                    intent = local_result["intent"]
                    if intent and intent != "other":
                        intents.add(intent)
        except Exception:
            pass  # 降级：不调本地模型，走云端

    return intents, local_result


def intents_from_tool_history(
    session_id: str, limit: int = 5
) -> set[str]:
    """从最近的工具调用记录中反推意图标签。

    覆盖“继续”“换个颜色”“再试一次”等短指令——此时用户消息本身
    不含领域关键词，但刚执行过的工具说明任务还在进行中。
    """
    try:
        recent_runs = db.recent_tool_runs(session_id, limit=limit)
    except Exception:  # noqa: BLE001 — 意图分类必须永不中断对话
        return set()
    return {
        _TOOL_TO_INTENT[run["tool_name"]]
        for run in recent_runs
        if run.get("tool_name") in _TOOL_TO_INTENT
    }


def build_rule_sections(
    intents: set[str],
    is_first_turn: bool,
) -> str:
    """按意图集合组装规则节文本。

    安全兜底：首轮且未识别到任何意图时注入完整 SYSTEM_PROMPT（保守策略，
    与旧版行为逐字节一致）；其余情况只注入核心节 + 命中意图的条件节。
    只要命中任一条件意图，就同时注入完整 options 卡片规范
    （条件流程都涉及让用户选择/确认）。
    """
    if is_first_turn and not intents:
        return SYSTEM_PROMPT

    parts: list[str] = list(ALWAYS_SECTIONS)
    if intents:
        parts.append(_OPTIONS_CARD_RULES)
    seen: set[str] = set()
    for intent in _INTENT_ORDER:
        if intent not in intents:
            continue
        for section in CONDITIONAL_SECTIONS[intent]:
            if section in seen:
                continue
            seen.add(section)
            parts.append(section)
    return "\n".join(parts)


def estimate_rule_sections_tokens(
    intents: set[str],
    is_first_turn: bool,
) -> int:
    """估算组装后规则节文本的 token 数（供 usage 环展示）。"""
    from .compact import estimate_tokens

    return estimate_tokens(build_rule_sections(intents, is_first_turn))
