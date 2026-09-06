from __future__ import annotations

# Agent 包共享的提示词与工具策略常量。
# 主提示词按规则域拆分在 prompt_sections.py（20 个有名字的节常量），
# 这里按固定顺序用 "\n" 拼接成 SYSTEM_PROMPT，拼接结果与旧版单一字符串逐字节一致。

from .prompt_sections import (
    _CHART_RULES,
    _DATA_TOOL_RULES,
    _DOCUMENT_RULES,
    _FILE_AND_WEB_RULES,
    _FILE_SEARCH_RULES,
    _GENERAL_RULES,
    _HTML_PAGE_RULES,
    _IMAGE_GENERATION_RULES,
    _MEMORY_RULES,
    _MERMAID_RULES,
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

# 拼接顺序 = 旧版 SYSTEM_PROMPT 中规则块的原始顺序；新增/调整规则时在此增删节。
SYSTEM_PROMPT = "\n".join((
    _GENERAL_RULES,
    _SKILL_RULES,
    _FILE_SEARCH_RULES,
    _IMAGE_GENERATION_RULES,
    _OPTIONS_CARD_RULES,
    _PDF_STYLE_RULES,
    _PDF_TRAVEL_RULES,
    _DOCUMENT_RULES,
    _RESUME_RULES,
    _PDF_RENDER_RULES,
    _DATA_TOOL_RULES,
    _MERMAID_RULES,
    _SVG_RULES,
    _UX_HTML_RULES,
    _HTML_PAGE_RULES,
    _CHART_RULES,
    _FILE_AND_WEB_RULES,
    _TERMINAL_RULES,
    _SUBAGENT_RULES,
    _PROJECT_WORKFLOW,
    _MEMORY_RULES,
))

_READ_ONLY_TOOLS = {
    "ask_user",
    "document_outline",
    "pdf_form_fields",
    "discover_importable_skills",
    "load_skill",
    "preview_skill_repo",
    "read_file",
    "read_image",
    "search_files",
    "grep_files",
    "directory_tree",
    "rag_search",
    "sqlite_query",
    "calculator",
    "web_fetch",
    "web_fetch_batch",
    "web_search",
    "generate_chart",
    "describe_svg",
    "git_status",
    "git_diff",
    "review_changes",
    "git_log",
    "bg_status",
    "bg_output",
}

_NO_PLAN_TOOLS = {
    "ask_user",
    "discover_importable_skills",
    "install_skill",
    "migrate_skill",
    "migrate_skills",
    "preview_skill_repo",
    "schedule_task",
    "write_calendar",
    "draw_svg",
    "edit_svg",
    "svg_to_png",
    "svg_to_png_batch",
    "remember",
    "forget_memory",
    "run_subagents",
    "git_commit",
    "git_revert",
    "bg_kill",
    "undo_last_turn",
}

MAX_TOOL_TURNS = 96

# LangGraph super-step 上限按调用预算推导：每个工具轮至少消耗模型节点 +
# 工具节点两个 super-step，并行工具调用与审批中断（interrupt→resume）还会
# 叠加。写死 256 时多工具任务会先于 96 次调用预算触发 GraphRecursionError，
# ModelCallLimit 的优雅收尾（exit_behavior="end"）形同虚设；子代理侧同款
# 公式见 subagents.py（SUBAGENT_MAX_TOOL_TURNS * 6）。
AGENT_RECURSION_LIMIT = MAX_TOOL_TURNS * 4

# 审批/提问等待用户决策的超时秒数：settings.json 的 approval_timeout 可覆盖，
# 下限 30s 防误配成 0 导致确认卡闪过即拒。
DEFAULT_APPROVAL_TIMEOUT_SECONDS = 180
_APPROVAL_TIMEOUT_FLOOR = 30


def approval_timeout_seconds(settings: dict | None) -> int:
    try:
        value = int((settings or {}).get("approval_timeout") or 0)
    except (TypeError, ValueError):
        return DEFAULT_APPROVAL_TIMEOUT_SECONDS
    if value <= 0:
        return DEFAULT_APPROVAL_TIMEOUT_SECONDS
    return max(value, _APPROVAL_TIMEOUT_FLOOR)

# 用户消息尾部的 options 卡片遵循提示（随本次模型输入注入，不落库不参与意图分类）。
# system prompt 侧规则对 deepseek 的遵循率不稳，用户消息尾部注入实测有效
# （与实时信息强制联网同一注入模式）。
OPTIONS_CARD_HINT = (
    "（系统提醒：若你的回答需要询问用户是否生成某产物或下一步做什么"
    "——需要我…吗/要不要我…/整理成 X 还是 Y——必须用 ```options 卡片，"
    "且候选动作不超过 3 个时，最后一项固定为 "
    "{\"label\": \"暂时不用\", \"action\": \"decline\"}"
    "（label 可按用户语言书写，action 必须是 decline），"
    "other 传 false，禁止纯文字提问；"
    "常规的风格/方案选择卡（4 个以上选项）不需要「暂时不用」。）"
)
