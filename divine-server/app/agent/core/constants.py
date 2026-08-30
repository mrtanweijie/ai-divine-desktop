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
    _CHART_RULES,
    _FILE_AND_WEB_RULES,
    _TERMINAL_RULES,
    _SUBAGENT_RULES,
    _PROJECT_WORKFLOW,
    _MEMORY_RULES,
))

_READ_ONLY_TOOLS = {
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
