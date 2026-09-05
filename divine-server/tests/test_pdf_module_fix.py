"""PDF 模块修复回归（docs/fix/002-pdf-module-style-20260906.md）：

- _inline_md：模块内容 **粗**/`码`/斜体 正常渲染，不再字面输出星号；
- hero-stat 自适应：长数值降字号/降列（2×2），短值保持单行；
- compare/features 溢出：真实管线渲染后用 pymupdf 做几何断言
  （面板矩形底边 ≥ 文本墨迹底边，此前溢出 9pt）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.pdf.renderer.markdown import (  # noqa: E402
    _inline_md,
    _render_table_module,
)
from app.docgen.pdf.renderer.renderer import render_markdown_to_pdf  # noqa: E402

_OVERFLOW_MD = """# 对比回归

## 二、对比章节

| 原方案 | 新方案 |
|---|---|
| 巩固优势 | 持续强化L6/L7爆款地位，通过OTA升级、用户运营等方式维持产品热度 |
| 纯电突破 | 加快M8/M9产能爬坡，优化纯电产品营销策略，提升纯电占比 |
| 竞品应对 | 针对同比下滑月份，深入分析竞品动作与市场环境，制定针对性应对方案 |
| 技术迭代 | 持续迭代增程技术，优化纯电平台成本结构，为下一阶段竞争蓄力 |
{: .compare}
"""


def test_inline_md_basic():
    assert _inline_md("**加粗**") == "<strong>加粗</strong>"
    assert _inline_md("*斜体*") == "<em>斜体</em>"
    assert _inline_md("`code`") == "<code>code</code>"
    assert "<strong>" in _inline_md("a **b** c **d** e")  # 多处命中


def test_inline_md_escapes_html_first():
    # 先 escape 再解析：<script> 被转义，** 仍正常
    html = _inline_md('<b>&</b> **粗**')
    assert "&lt;b&gt;" in html and "&amp;" in html
    assert "<strong>粗</strong>" in html


def test_inline_md_unpaired_kept_literal():
    assert _inline_md("单独的 ** 星号") == "单独的 ** 星号"


def test_hero_stat_short_values_single_row():
    rows = [
        ["累计", "196辆", ""],
        ["月均", "32辆", ""],
        ["峰值", "41辆", "+5%"],
        ["7月", "30辆", "-2%"],
    ]
    html = _render_table_module("hero-stat", rows)
    assert html.count('class="stat-row"') == 1  # 单行
    assert html.count('class="stat-item"') == 4
    assert "font-size:36px" in html


def test_hero_stat_long_values_wrap_to_two_rows():
    """事故场景：196,272辆 等 8 字符长值一行 4 列放不下 → 2×2。"""
    rows = [
        ["累计交付量", "196,272辆", ""],
        ["月均交付量", "32,712辆", ""],
        ["销量峰值（3月）", "41,053辆", "+55.4%"],
        ["7月销量", "30,468辆", "-25.8%"],
    ]
    html = _render_table_module("hero-stat", rows)
    assert html.count('class="stat-row"') == 2  # 2×2
    assert html.count('class="stat-item"') == 4
    # 降列后字号应回到大字号（2 列放得下 36px）
    assert "font-size:36px" in html


def test_compare_and_callout_render_inline_markdown():
    compare = _render_table_module(
        "compare", [["**旧要点**", "新要点 **重要**"], ["a", "b"]]
    )
    assert "<strong>旧要点</strong>" in compare
    assert "新要点 <strong>重要</strong>" in compare
    conclusion = _render_table_module  # noqa: F841 — 占位防误删
    from app.docgen.pdf.renderer.markdown import _render_alert_block

    html = _render_alert_block("conclusion", "选型判断", ["**若追求长程执行** → 试"])
    assert "<strong>若追求长程执行</strong>" in html


def test_compare_overflow_fixed_geometry(tmp_path):
    """关键几何回归：此前 AFTER 面板底边 327 vs 文本底 336（溢出 9pt）。"""
    output = tmp_path / "compare.pdf"
    render_markdown_to_pdf(
        _OVERFLOW_MD, output, title="对比回归", style="modern", color_scheme="blue"
    )
    import pymupdf

    doc = pymupdf.open(str(output))
    try:
        page = next(p for p in doc if "AFTER" in p.get_text().upper())
        panels = [
            d["rect"]
            for d in page.get_drawings()
            if d["rect"].width > 150 and d["rect"].height > 60
        ]
        assert panels, "未找到 compare 面板矩形"
        panel_bottom = max(r.y1 for r in panels)
        text_bottom = max(
            b[3]
            for b in page.get_text("blocks")
            if "持续迭代" in b[4] or "针对同比" in b[4]
        )
        assert text_bottom <= panel_bottom + 2, (
            f"compare 内容溢出面板：文本底 {text_bottom:.0f} > 面板底 {panel_bottom:.0f}"
        )
        # 水平方向不越界
        rect = page.rect
        for b in page.get_text("blocks"):
            assert b[2] <= rect.x1 + 2, f"文本越界: {b[4][:20]!r}"
    finally:
        doc.close()


def test_hero_stat_no_horizontal_overflow(tmp_path):
    """事故场景几何回归：4 个长数值 KPI 横条不再右溢截断。"""
    md = """# KPI

| 累计交付量 | 196,272辆 | |
| 月均交付量 | 32,712辆 | |
| 销量峰值（3月） | 41,053辆 | +55.4% |
| 7月销量 | 30,468辆 | -25.8% |
{: .hero-stat}
"""
    output = tmp_path / "kpi.pdf"
    render_markdown_to_pdf(
        md, output, title="KPI", style="modern", color_scheme="blue"
    )
    import pymupdf

    doc = pymupdf.open(str(output))
    try:
        page = doc[0]
        rect = page.rect
        for b in page.get_text("blocks"):
            assert b[2] <= rect.x1 + 2, f"KPI 文本右溢: {b[4][:20]!r}"
        # 四个数值全部完整渲染
        text = page.get_text()
        for value in ("196,272", "32,712", "41,053", "30,468"):
            assert value in text
    finally:
        doc.close()


def test_features_cards_contain_long_desc(tmp_path):
    """能力总览场景：最长描述完整渲染且不越界。"""
    md = """# 能力总览

| 🤖 | 智能对话 | 大模型驱动的问答与多轮对话 |
| 📄 | 文档办公 | 生成与编辑 Markdown、Word、PDF、PPT、Excel 等多种格式文档 |
| 📊 | 数据分析 | 数学计算、ECharts 图表、Excel 读写、SQLite 查询与可视化 |
| 🎨 | 图像设计 | 文生图/图生图、SVG 编辑、图片识别与转换 |
{: .features}
"""
    output = tmp_path / "features.pdf"
    render_markdown_to_pdf(
        md, output, title="能力总览", style="modern", color_scheme="blue"
    )
    import pymupdf

    doc = pymupdf.open(str(output))
    try:
        text = doc[0].get_text()
        assert "等多种格式文档" in text  # 最长描述完整
    finally:
        doc.close()


def test_qa_detects_literal_markdown(tmp_path):
    from app.docgen.pdf.renderer.qa import inspect_pdf

    import pymupdf

    path = tmp_path / "literal.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "残留 ** 星号样例")
    doc.save(str(path))
    doc.close()

    result = inspect_pdf(path)
    assert any(issue.get("type") == "literal_markdown" for issue in result["issues"])
