"""Intent classification and rule-section selection tests."""

from pathlib import Path


def _init(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "intent.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    return db


# ---------------------------------------------------------------------------
# classify_intents
# ---------------------------------------------------------------------------

def test_classify_basic_intents():
    from app.agent.intent import classify_intents

    intents, _ = classify_intents("帮我生成一份日本旅行攻略的PDF")
    assert "pdf" in intents
    intents, _ = classify_intents("我想做个旅行手册，带封面和主题色")
    assert "pdf" in intents
    intents, _ = classify_intents("帮我写一份求职简历")
    assert "resume" in intents
    intents, _ = classify_intents("做一个产品介绍的PPT")
    assert "document" in intents
    intents, _ = classify_intents("帮我生成一张海报图片")
    assert "image" in intents
    intents, _ = classify_intents("画一个SVG图标")
    assert "svg" in intents
    intents, _ = classify_intents("把这几组数据画成柱状图")
    assert "chart" in intents
    intents, _ = classify_intents("画个流程图说明逻辑")
    assert "mermaid" in intents
    intents, _ = classify_intents("把这个PRD做成UX交互原型")
    assert "ux" in intents
    intents, _ = classify_intents("从 Claude Code 迁移技能")
    assert "skill" in intents
    intents, _ = classify_intents("帮我执行命令安装依赖")
    assert "terminal" in intents
    intents, _ = classify_intents("用并行子任务同时调研多个来源")
    assert "subagent" in intents
    intents, _ = classify_intents("记住我的偏好")
    assert "memory" in intents


def test_classify_case_insensitive_english():
    from app.agent.intent import classify_intents

    intents, _ = classify_intents("Generate a PDF for me")
    assert "pdf" in intents
    intents, _ = classify_intents("Help me with my RESUME")
    assert "resume" in intents
    intents, _ = classify_intents("Make a Word document")
    assert "document" in intents
    intents, _ = classify_intents("Draw an SVG logo")
    assert "svg" in intents
    intents, _ = classify_intents("Show trend with ECharts")
    assert "chart" in intents


def test_project_intent_precision():
    """project 意图需强关键词 >=1 或弱关键词 >=2，避免误触发。"""
    from app.agent.intent import classify_intents

    # 单弱关键词（"代码"）不应触发 —— 只是解释提问
    intents, _ = classify_intents("这段代码什么意思？")
    assert "project" not in intents
    # 强关键词触发
    intents, _ = classify_intents("帮我重构这个模块")
    assert "project" in intents
    intents, _ = classify_intents("修复那个bug")
    assert "project" in intents
    intents, _ = classify_intents("帮我开发一个登录功能")
    assert "project" in intents
    # 两个弱关键词触发
    intents, _ = classify_intents("这个项目的代码结构怎么优化")
    assert "project" in intents
    # 弱关键词只有 1 个时不触发
    intents, _ = classify_intents("看一下这个文件")
    assert "project" not in intents


def test_classify_no_false_positive_plain_chat():
    from app.agent.intent import classify_intents

    intents, _ = classify_intents("今天天气怎么样")
    assert intents == set()
    intents, _ = classify_intents("帮我翻译这句话")
    assert intents == set()
    intents, _ = classify_intents("你好")
    assert intents == set()


def test_classify_history_context_for_deictic_followup():
    """短指令（"换个颜色"）借助最近 AI 回复尾部回补意图。"""
    from app.agent.intent import classify_intents

    ai_tail = "已为你生成旅行手册 PDF，主题色当前是 teal。"
    intents, _ = classify_intents("换个颜色", ai_tail)
    assert "pdf" in intents


# ---------------------------------------------------------------------------
# intents_from_tool_history
# ---------------------------------------------------------------------------

def test_intents_from_tool_history(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    session = db.create_session("Test", None)
    db.add_tool_run(session["id"], "pdf_generate", "done", {})
    db.add_tool_run(session["id"], "generate_chart", "done", {})

    from app.agent.intent import intents_from_tool_history

    assert intents_from_tool_history(session["id"], limit=5) == {
        "pdf",
        "chart",
    }
    # limit 窗口只取最近 N 条
    assert intents_from_tool_history(session["id"], limit=1) == {"chart"}
    # 无历史 -> 空集
    other = db.create_session("Other", None)
    assert intents_from_tool_history(other["id"], limit=5) == set()


def test_recent_tool_runs_order_and_limit(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    session = db.create_session("Test", None)
    for name in ("a", "b", "c"):
        db.add_tool_run(session["id"], name, "done", {})

    recent = db.recent_tool_runs(session["id"], limit=2)
    assert [run["tool_name"] for run in recent] == ["b", "c"]


# ---------------------------------------------------------------------------
# build_rule_sections
# ---------------------------------------------------------------------------

def test_first_turn_without_intent_injects_full_system_prompt():
    from app.agent.core import SYSTEM_PROMPT
    from app.agent.intent import build_rule_sections

    assert build_rule_sections(set(), is_first_turn=True) == SYSTEM_PROMPT


def test_later_turn_without_intent_injects_only_core():
    from app.agent.intent import (
        ALWAYS_SECTIONS,
        build_rule_sections,
    )
    from app.agent.core.prompt_sections import (
        _PDF_STYLE_RULES,
        _PDF_TRAVEL_RULES,
        _RESUME_RULES,
        _SKILL_RULES,
    )

    text = build_rule_sections(set(), is_first_turn=False)
    for section in ALWAYS_SECTIONS:
        assert section in text
    # 条件节不应出现
    for section in (_PDF_STYLE_RULES, _PDF_TRAVEL_RULES, _RESUME_RULES, _SKILL_RULES):
        assert section not in text
    # 完整 options 规范不应出现（只有精简版常驻）
    from app.agent.core.prompt_sections import _OPTIONS_CARD_RULES

    assert _OPTIONS_CARD_RULES not in text


def test_intent_injects_conditional_sections_only():
    from app.agent.intent import ALWAYS_SECTIONS, build_rule_sections
    from app.agent.core.prompt_sections import (
        _OPTIONS_CARD_RULES,
        _PDF_STYLE_RULES,
        _PDF_TRAVEL_RULES,
        _RESUME_RULES,
    )

    text = build_rule_sections({"pdf"}, is_first_turn=False)
    for section in ALWAYS_SECTIONS:
        assert section in text
    assert _PDF_STYLE_RULES in text
    assert _PDF_TRAVEL_RULES in text
    assert _RESUME_RULES not in text
    # 条件流程附带完整 options 规范
    assert _OPTIONS_CARD_RULES in text


def test_multi_intent_assembles_all_and_dedupes():
    from app.agent.intent import build_rule_sections
    from app.agent.core.prompt_sections import (
        _CHART_RULES,
        _PDF_STYLE_RULES,
        _RESUME_RULES,
        _SVG_RULES,
    )

    text = build_rule_sections({"pdf", "resume", "chart", "svg"}, is_first_turn=False)
    for section in (_PDF_STYLE_RULES, _RESUME_RULES, _CHART_RULES, _SVG_RULES):
        assert section in text
    # 无重复节（每节只出现一次）
    for section in (_PDF_STYLE_RULES, _RESUME_RULES):
        assert text.count(section) == 1


def test_options_mini_kept_in_core_and_full_only_conditional():
    """P2：精简版常驻，完整版仅条件注入。"""
    from app.agent.intent import ALWAYS_SECTIONS, build_rule_sections
    from app.agent.core.prompt_sections import (
        _OPTIONS_CARD_MINI_RULES,
        _OPTIONS_CARD_RULES,
    )

    assert _OPTIONS_CARD_MINI_RULES in ALWAYS_SECTIONS
    core = build_rule_sections(set(), is_first_turn=False)
    assert _OPTIONS_CARD_MINI_RULES in core
    assert _OPTIONS_CARD_RULES not in core

    conditional = build_rule_sections({"resume"}, is_first_turn=False)
    assert _OPTIONS_CARD_RULES in conditional


def test_full_system_prompt_regression():
    """回归：SYSTEM_PROMPT 保持旧版逐字节一致——含全部 20 节、不含新加的迷你版。"""
    from app.agent.core import prompt_sections as ps
    from app.agent.core import SYSTEM_PROMPT

    section_names = [
        name
        for name in dir(ps)
        if name.startswith("_") and name.endswith("_RULES")
    ]
    mini = "_OPTIONS_CARD_MINI_RULES"
    full_names = [name for name in section_names if name != mini]
    assert mini in section_names  # 迷你版存在于模块
    assert getattr(ps, mini) not in SYSTEM_PROMPT  # 但不属于 SYSTEM_PROMPT

    # 其余每节恰好出现一次（保持无重复）
    for name in full_names:
        assert SYSTEM_PROMPT.count(getattr(ps, name)) == 1, name
    assert ps._OPTIONS_CARD_RULES in SYSTEM_PROMPT  # 完整版仍属于 SYSTEM_PROMPT


def test_estimate_rule_sections_tokens():
    from app.agent.intent import estimate_rule_sections_tokens

    full = estimate_rule_sections_tokens(set(), is_first_turn=True)
    core = estimate_rule_sections_tokens(set(), is_first_turn=False)
    pdf = estimate_rule_sections_tokens({"pdf"}, is_first_turn=False)
    assert full > core
    assert pdf > core
    assert core > 0


def test_excel_table_routes_to_document():
    """Excel/表格族消息必须命中 document 意图（注入 spreadsheet 工具）。

    原缺陷：关键词表漏掉 excel/表格/对比表 → 意图空 → 模型只能写
    Python 脚本 + pip install openpyxl 生成 xlsx。
    """
    from app.agent.intent import classify_intents

    for text in (
        "生成总价格对比表（含全部档位 Excel）",
        "生成同行业对比表（宇树/智元/优必选/特斯拉 Excel）",
        "整理成 Excel 表格",
        "做一份价格对比表",
        "帮我做个汇总表",
    ):
        intents, _ = classify_intents(text)
        assert "document" in intents, f"{text!r} 应命中 document：{intents}"


def test_spreadsheet_rules_present_in_document_section():
    """document 规则节必须教模型用 spreadsheet 工具（而非写脚本生成 xlsx）。"""
    from app.agent.core.prompt_sections import _DOCUMENT_RULES

    assert "spreadsheet" in _DOCUMENT_RULES
    assert "openpyxl" in _DOCUMENT_RULES  # 禁止绕路的明确指令


def test_html_routes_to_html_intent():
    """HTML 文件产出请求必须命中 html 意图（注入 _HTML_PAGE_RULES）。

    原缺陷：模型用 write_file 直接写 .html，绕过 html_generate 的 token 基座
    注入与静态校验——「单页 HTML」这类请求零关键词命中，既无规范节、
    也无对应工具信号。新增 html 意图后应命中。
    """
    from app.agent.intent import classify_intents

    for text in (
        "帮我做一份「持仓体检」单页 HTML",
        "生成一个数据看板",
        "写一个落地页",
        "做个仪表盘",
    ):
        intents, _ = classify_intents(text)
        assert "html" in intents, f"{text!r} 应命中 html：{intents}"


def test_html_generate_resident_not_trimmed():
    """html_generate 必须常驻（不进 _CONTENT_TOOLS），避免意图漏判导致工具缺失。

    与 ux_html 的定位差异：ux_html 是纯内容创作、按 ux 意图裁剪；html_generate
    覆盖「产出一个 HTML 文件」的普适场景，必须像 write_file 一样常驻。
    """
    from app.agent.tools.tools import _CONTENT_TOOLS

    assert "html_generate" not in _CONTENT_TOOLS
    assert "ux_html" in _CONTENT_TOOLS  # 对照：UX 原型仍按意图裁剪


def test_html_generate_tool_history_backfills_html():
    """工具历史回补：调用过 html_generate 后，「继续/换个风格」等短指令能回补 html 意图。"""
    from app.agent.intent.intent import _TOOL_TO_INTENT

    assert _TOOL_TO_INTENT.get("html_generate") == "html"


def test_html_intent_injects_html_generate_rules():
    """html 意图命中时，_HTML_PAGE_RULES 应注入；未命中时不注入。"""
    from app.agent.intent import build_rule_sections
    from app.agent.core.prompt_sections import _HTML_PAGE_RULES

    hit = build_rule_sections({"html"}, is_first_turn=False)
    assert _HTML_PAGE_RULES in hit

    miss = build_rule_sections(set(), is_first_turn=False)
    assert _HTML_PAGE_RULES not in miss
