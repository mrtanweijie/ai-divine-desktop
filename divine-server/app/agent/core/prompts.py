"""Dynamic prompts, RAG context, skill catalog, and plan-asking heuristics."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ... import db
from ...config import settings_store
from ...db.retrieval import rank_documents
from ...localization import language_instruction
from ...skills import skill_registry
from .constants import MAX_TOOL_TURNS
from .context import AgentRunContext
from ..intent import (
    classify_intents,
    intents_from_tool_history,
    split_rule_sections,
)
from .llm import _resolve_model_entry
from ..rag import _auto_rag_context
from .schema import _content_text, _skill_tool_name
from ..state import _plan_progress

logger = logging.getLogger("divine.agent.prompts")

# ReAct 文本工具调用模式提示词。定义在 core（prompts）而非 react：prompts
# 是 core 层、react 属于 tools 子包，若常量留在 react，core → tools 与
# tools → core 会构成包级循环导入（消除 prompts↔react 惰性环）。
REACT_FORMAT_PROMPT = """【ReAct 文本工具调用模式】
当前模型不启用原生函数调用，需要调用工具时按以下格式逐行输出（关键词固定为英文）：
Thought: 推理
Action: 工具名
Action Input: {"参数": 值}
工具执行结果会以 Observation 形式返回给你；根据结果继续 Thought → Action，直到完成；
完成时以 “Final Answer: ” 开头输出最终回答。
规则：
- Action 只能使用系统提供的工具名，Action Input 必须是合法 JSON 且与工具参数定义一致；
  参数不确定时先用 read_file / search_files 了解情况，不要编造；
- 每轮只输出一个 Action；不要输出 XML/伪代码形式的调用；不要杜撰工具；
- 正文中的普通解释文字可以正常输出，但不要与 Action 格式混淆。"""

_PLAN_CONTINUATION_KEYWORDS = (
    "继续",
    "下一步",
    "执行计划",
    "按计划",
    "开始执行",
    "接着",
    "往下",
    "continue",
    "next step",
)

_MEMORY_CATEGORY_LABELS = {
    "preference": "偏好",
    "fact": "事实",
    "event": "事件",
}

# Hard cap for the injected memory block (tokens ≈ chars / 1.5 for CJK).
_MEMORY_BLOCK_CHAR_LIMIT = 2200

# 回溯提问快路径关键词：命中时放宽触发条件（无需显著优于窗口）。
# 关键词只作加速，不承担召回完整性——未命中的表达由"检索对比"兜底。
_BACKTRACK_KEYWORDS = (
    "之前",
    "刚才",
    "以前",
    "前面",
    "第一次",
    "那时",
    "原来",
    "一开始",
    "说过",
    "聊过",
    "上次",
    "还记得",
)

# 会话历史回溯块预算（与记忆块同量级，token ≈ chars / 1.5）。
_HISTORY_BACKTRACK_CHAR_LIMIT = 1200
# 单条命中片段上限，超出截断。
_HISTORY_SNIPPET_CHAR_LIMIT = 200
# 最低相关度：低于此值的 TF-IDF 余弦视为噪声，不注入（宁可漏，不可污染）。
_HISTORY_BACKTRACK_MIN_SCORE = 0.08
# 窗口大小：与上下文治理的"最近 12 条完整保留"对齐——窗口内内容本就在
# LLM 上下文里，回溯只关心窗口外命中的早期片段。
_HISTORY_WINDOW_SIZE = 12
# 无关键词时，早期命中须显著优于窗口内命中才注入（否则窗口内上下文已足够）。
_HISTORY_BACKTRACK_MARGIN = 0.08
# 无关键词且窗口内已足够贴切（当前话题直接能答）时，跳过全历史检索省成本。
_HISTORY_WINDOW_SKIP_THRESHOLD = 0.6

# 被动注入的查询源轮数：只取最后一条会被“那还用刚才说的那个方案吗”这类
# 指代性提问打空，取最近几条拼接后 TF-IDF 天然按词聚合。
_MEMORY_QUERY_MESSAGES = 3

def _memory_context(
    messages: list[Any], project_id: str | None = None
) -> str | None:
    """Build a compact 'known user info' block from long-term memories.

    The last few user messages drive similarity search (referential
    questions like “还是刚才那个吗” need earlier turns too); ranking mixes
    similarity with importance/recency inside db.search_memories. When the
    session belongs to a project, project-scoped memories rank first while
    global ones keep reserved slots; other projects' memories are excluded.
    Output is bounded so the system prompt never balloons.
    """
    recent_user_texts: list[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _content_text(message.content).strip()
            if text:
                recent_user_texts.append(text)
            if len(recent_user_texts) >= _MEMORY_QUERY_MESSAGES:
                break
    query_text = " ".join(reversed(recent_user_texts))
    try:
        hits = db.search_memories(query_text, limit=5, project_id=project_id)
    except Exception:  # noqa: BLE001 — memory must never break the agent
        return None
    if not hits:
        return None
    try:
        db.touch_memory_access(
            [str(memory.get("id") or "") for memory in hits]
        )
    except Exception:  # noqa: BLE001 — recency refresh is best-effort
        pass
    lines: list[str] = []
    used = 0
    for memory in hits:
        label = _MEMORY_CATEGORY_LABELS.get(
            str(memory.get("category") or ""), "记忆"
        )
        content = str(memory.get("content") or "").strip()
        if not content:
            continue
        line = f"- [{label}] {content}（id: {memory.get('id')}）"
        if used + len(line) > _MEMORY_BLOCK_CHAR_LIMIT:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return None
    header = "## 关于你已知的用户信息（自然运用，不要刻意提及；若与用户当前说法冲突，以用户当前说法为准）"
    return header + "\n" + "\n".join(lines)


def _session_project_id(session_id: str) -> str | None:
    """会话所属项目 id（记忆项目作用域用）；查不到返回 None（仅全局记忆）。"""
    try:
        session = db.get_session(session_id)
    except Exception:  # noqa: BLE001 — scoping must never break a turn
        return None
    if not session:
        return None
    return str(session.get("project_id") or "") or None


def _top_score(query: str, docs: list[str]) -> float:
    """TF-IDF 余弦 top1 得分；无命中返回 0。"""
    hits = rank_documents(query, docs, top_k=1)
    return hits[0][0] if hits else 0.0


def _history_backtrack_context(
    session_id: str, query: str, limit: int = 3
) -> str | None:
    """回溯提问时，从本会话全量历史中检索相关片段并注入。

    触发逻辑（B 方案：关键词快路径 + 检索对比兜底）：
    - 关键词命中（"之前/刚才/说过/还记得"等）：历史检索 top1 高于噪声阈值即注入
      ——快路径，但最终仍由相关度把关，避免误触发。
    - 未命中关键词：早期片段须**显著优于窗口内命中**（差值 margin）才注入——
      因为窗口内容本就在 LLM 上下文里，只有"窗口外的答案"才值得补。
    - 窗口内已足够贴切（top ≥ 0.6）且无关键词：跳过全历史检索，省成本。

    数据源是 ``db.list_messages``（全量历史，含窗口外消息），TF-IDF 余弦打分
    （``app.db.retrieval``），注入时跳过窗口内片段（避免重复占用预算），输出
    受预算约束的参考块。任何异常都不应打断对话，返回 None。
    """
    query = (query or "").strip()
    if not session_id or not query:
        return None
    keyword_hit = any(
        keyword in query for keyword in _BACKTRACK_KEYWORDS
    )
    try:
        rows = db.list_messages(session_id)
    except Exception:  # noqa: BLE001 — retrieval must never break a turn
        logger.exception("history backtrack load failed")
        return None
    docs: list[str] = []
    for row in rows:
        role = str(row.get("role") or "")
        content = str(row.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        docs.append(content)
    if len(docs) < 2:
        return None

    window = docs[-_HISTORY_WINDOW_SIZE:]
    window_top = _top_score(query, window)
    if not keyword_hit and window_top >= _HISTORY_WINDOW_SKIP_THRESHOLD:
        return None  # 当前话题贴切，直接能答，无需回溯

    hits = rank_documents(query, docs, top_k=max(1, limit * 2))
    if not hits:
        return None
    history_top = hits[0][0]
    if history_top < _HISTORY_BACKTRACK_MIN_SCORE:
        return None
    if not keyword_hit and not (
        history_top > window_top + _HISTORY_BACKTRACK_MARGIN
    ):
        return None  # 早期没有显著优于窗口的答案

    # 注入：跳过窗口内 index（已在 LLM 上下文里，避免重复占用预算）。
    window_indices = set(range(len(docs) - len(window), len(docs)))
    lines: list[str] = []
    used = 0
    for score, index in hits:
        if score < _HISTORY_BACKTRACK_MIN_SCORE:
            break  # 降序排列，后续只会更低
        if index in window_indices:
            continue
        snippet = docs[index].replace("\n", " ")[:_HISTORY_SNIPPET_CHAR_LIMIT]
        line = f"- (相关度 {score:.2f}) {snippet}"
        if used + len(line) > _HISTORY_BACKTRACK_CHAR_LIMIT:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return None
    header = "## 会话历史中与回溯提问相关的片段（供参考，可能来自早期对话）"
    return header + "\n" + "\n".join(lines)

def _auto_rag_context_lc(
    messages: list[Any], workspace: Path
) -> str | None:
    history: list[dict[str, Any]] = []
    for message in messages:
        role = getattr(message, "type", "")
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        elif role == "tool":
            role = "tool"
        else:
            continue
        content = _content_text(getattr(message, "content", ""))
        if not content:
            continue
        history.append({"role": role, "content": content})
    return _auto_rag_context(history, workspace)

def _skill_catalog_prompt() -> str:
    knowledge_skills = skill_registry.knowledge_skills()
    executable_skills = skill_registry.executable_skills()
    if not knowledge_skills and not executable_skills:
        return ""
    lines: list[str] = []
    if knowledge_skills:
        lines.append("可用知识技能（需要时调用 load_skill 加载正文和参考资料）：")
        for skill in knowledge_skills:
            lines.append(f"- {skill.name}: {skill.description}")
    if executable_skills:
        lines.append("可用能力技能（可直接调用脚本工具执行）：")
        for skill in executable_skills:
            tool_name = _skill_tool_name(skill.name)
            if skill.script_mode == "json":
                usage = "从 stdin 读取 JSON 参数"
            else:
                usage = "接收命令行参数 args"
            lines.append(
                f"- {skill.name}: {skill.description}"
                f"（调用 {tool_name}，{usage}）"
            )
    return "\n".join(lines)

def _active_plan_progress(
    messages: list[Any], todos: list[dict[str, Any]]
) -> str | None:
    if not todos:
        return None
    last_user_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_user_index = index
    if last_user_index < 0:
        return _plan_progress(todos)

    question = _content_text(messages[last_user_index].content).lower()
    if any(
        keyword in question for keyword in _PLAN_CONTINUATION_KEYWORDS
    ):
        return _plan_progress(todos)

    for message in messages[last_user_index + 1 :]:
        if isinstance(message, ToolMessage) and getattr(
            message, "name", None
        ) == "write_todos":
            return _plan_progress(todos)
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            name = call.get("name") if isinstance(call, dict) else getattr(
                call, "name", ""
            )
            if name == "write_todos":
                return _plan_progress(todos)
    return None

_PLAN_EXPLICIT_KEYWORDS = (
    "先出方案",
    "出方案",
    "做方案",
    "写方案",
    "给个方案",
    "制定计划",
    "做个计划",
    "做计划",
    "规划",
    "方案",
)

_NO_PLAN_EXPLICIT_KEYWORDS = (
    "不要方案",
    "不用方案",
    "不需要方案",
    "别问",
    "直接执行",
    "直接做",
    "直接完成",
    "不用计划",
    "不要计划",
)

_COMPLEX_PLAN_KEYWORDS = (
    "重构",
    "迁移",
    "搭建",
    "开发",
    "创建项目",
    "生成项目",
    "整个项目",
    "项目结构",
    "全栈",
    "多文件",
    "多个文件",
    "多页面",
    "多个页面",
    "多步",
    "多步骤",
    "批量",
    "所有文件",
    "全部文件",
    "完整",
    "复杂",
    "系统",
    "模块",
    "功能",
    "页面",
    "前端",
    "后端",
    "数据库",
    "接口",
    "组件",
    "网站",
    "应用",
    "脚手架",
    "框架",
    "教程",
    "目录结构",
)

def _should_ask_plan(messages: list[Any]) -> bool:
    user_messages = [
        message
        for message in messages
        if isinstance(message, HumanMessage)
    ]
    if not user_messages:
        return True
    text = _content_text(user_messages[-1].content).strip()
    if not text:
        return True
    lowered = text.lower()
    if any(keyword in lowered for keyword in _NO_PLAN_EXPLICIT_KEYWORDS):
        return False
    if any(keyword in lowered for keyword in _PLAN_EXPLICIT_KEYWORDS):
        return True

    score = 0
    if len(text) >= 100:
        score += 1
    score += sum(
        1 for keyword in _COMPLEX_PLAN_KEYWORDS if keyword in lowered
    )
    separators = sum(
        1
        for separator in ("、", "，", "和", "以及", "还要", "同时", "\n")
        if separator in text
    )
    if separators >= 2:
        score += 1
    if text.count("文件") >= 2 or text.count("页面") >= 2:
        score += 1
    return score >= 2

def _build_dynamic_prompt(ctx: AgentRunContext) -> Any:
    @dynamic_prompt
    def prompt(request: ModelRequest) -> str:
        current_settings = settings_store.load()
        provider = current_settings.get("provider") or "auto"
        # 用本次请求实际使用的模型（model_id 展开解析），而不是 active 默认模型；
        # 否则切换模型后 AI 仍自称默认模型（如 mimo-v2.5-pro）。
        entry = _resolve_model_entry(current_settings, ctx.model_id)
        model_name = entry.get("model") or "deepseek-v4-flash"
        if provider == "mock" or (
            provider == "auto" and not current_settings.get("api_key")
        ):
            model_line = "当前模型：本地演示模式（Mock）"
        else:
            model_line = f"当前模型：{model_name}"

        # --- 意图分类：按用户最新消息（+ 最近 AI 回复尾部）选择注入的规则节 ---
        messages = request.state.get("messages") or []
        last_user_text = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                last_user_text = _content_text(message.content)
                break
        last_ai_text = ""
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                last_ai_text = _content_text(message.content)[:500]
                break
        intents, _ = classify_intents(last_user_text, last_ai_text)
        if not intents:
            # 短指令（“换个颜色”“继续”）回补最近工具调用的意图
            intents = intents_from_tool_history(ctx.session_id, limit=5)
        # 首轮判定：会话里还没有历史用户消息（不含当前这条）
        human_count = sum(
            1
            for message in messages
            if isinstance(message, HumanMessage)
        )
        is_first_turn = human_count <= 1
        # 缓存友好排序：稳定节（ALWAYS_SECTIONS）在最前，让 DeepSeek/GLM 的
        # 前缀缓存命中；按轮变化的项目/计划/记忆/RAG 块随后；意图条件节放
        # 尾部——意图在轮间变化时不会打断前缀。
        rule_sections, conditional_sections = split_rule_sections(
            intents, is_first_turn
        )

        parts = [
            rule_sections.replace("create_plan", "write_todos"),
            language_instruction(ctx.locale),
            (
                f"当前桌面端 UI 主题：{ctx.ui_theme}。"
                "生成 SVG 架构图等定色产物时必须匹配此主题，详见 SVG 规则。"
            ),
            (
                f"当前会话所属项目工作目录：{ctx.workspace}\n"
                "请以该目录作为方案设计和文件操作的工作区。"
            ),
            model_line,
        ]
        try:
            from ..middleware import build_project_context

            project_block = build_project_context(ctx.workspace, ctx.session_id)
            if project_block:
                parts.append(project_block)
        except Exception:  # noqa: BLE001 — injection must never break a turn
            logger.exception("project context injection failed")
        todos = db.list_todos(ctx.session_id)
        plan_progress = _active_plan_progress(
            request.state.get("messages") or [], todos
        )
        if plan_progress:
            parts.append(plan_progress)
        memory_block = _memory_context(
            request.state.get("messages") or [],
            project_id=_session_project_id(ctx.session_id),
        )
        if memory_block:
            parts.append(memory_block)
        history_block = _history_backtrack_context(ctx.session_id, last_user_text)
        if history_block:
            parts.append(history_block)
        rag_context = _auto_rag_context_lc(
            request.state.get("messages") or [], ctx.workspace
        )
        if rag_context:
            parts.append(rag_context)
        skill_catalog = _skill_catalog_prompt()
        if skill_catalog:
            parts.append(skill_catalog)
        if conditional_sections:
            parts.append(
                conditional_sections.replace("create_plan", "write_todos")
            )
        if ctx.tool_mode == "react":
            parts.append(REACT_FORMAT_PROMPT)

        # 尾部固定提醒：后续询问必须用 options 卡片（含暂时不用，other=false）
        from ..core.prompt_sections import _FOLLOWUP_CARD_TAIL

        parts.append(_FOLLOWUP_CARD_TAIL)

        # 回合预算软着陆：接近 ModelCallLimit/ToolCallLimit 上限时提醒模型
        # 收尾汇报，而不是被上限静默截断（P3-3c）。
        ai_count = 0
        tool_call_count = 0
        for message in messages:
            if isinstance(message, AIMessage):
                ai_count += 1
                tool_call_count += len(message.tool_calls or [])
        remaining = min(
            MAX_TOOL_TURNS - ai_count, MAX_TOOL_TURNS - tool_call_count
        )
        if 0 < remaining <= 6:
            parts.append(
                f"【回合预算提醒】本任务剩余执行回合约 {remaining} 次。"
                "请立即收尾：不要再开启新的大步骤，完成手头这一小步后输出进度总结"
                "（已完成什么、验证结果如何、还剩什么没做），"
                "并告知用户回复“继续”即可接续执行剩余工作。"
            )
        return "\n\n".join(parts)

    return prompt
