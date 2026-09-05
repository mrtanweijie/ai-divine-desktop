"""旧版 8 主题渲染回归：竖线泄漏、编造百分比、跨页、断页与样式修复。"""

import pytest

from app.docgen.resume.models import ResumeData
from app.docgen.resume.renderers import _RENDERERS
from app.docgen.resume.renderers.helpers import skill_pairs_and_plain
from app.docgen.resume.sample_data import SAMPLE_RESUME

LEGACY_THEMES = [
    "professional",
    "creative",
    "minimal",
    "boss_zhipin",
    "finance",
    "linkedin",
    "kami",
    "kami_white",
]


def _body(theme: str) -> str:
    return _RENDERERS[theme](ResumeData.from_dict(SAMPLE_RESUME))


def test_skill_pairs_and_plain_splits_labeled_lines():
    pairs, plain = skill_pairs_and_plain(_resume := ResumeData.from_dict(SAMPLE_RESUME))
    # 示例数据 skills 为 "分类|内容" 行
    assert pairs and pairs[0][0] == "核心语言"
    assert "|" not in pairs[0][1]
    assert plain == []


def test_skill_pairs_and_plain_falls_back_to_core_skills():
    resume = ResumeData.from_dict({"name": "测试", "core_skills": ["Python", "SQL"]})
    pairs, plain = skill_pairs_and_plain(resume)
    assert pairs == [] and plain == ["Python", "SQL"]


@pytest.mark.parametrize("theme", LEGACY_THEMES)
def test_no_pipe_leak_in_rendered_html(theme: str):
    body = _body(theme)
    assert "核心语言|" not in body
    assert "后端框架|" not in body


@pytest.mark.parametrize("theme", ["creative", "professional"])
def test_no_fabricated_skill_percentage(theme: str):
    body = _body(theme)
    assert "80%" not in body


def test_creative_paginates_without_blank_first_page():
    """回归：flex 双栏曾整体被搬到第 2 页导致首页大面积空白。"""
    from app.docgen.resume.theme_css.creative import CREATIVE_CSS

    assert "display: table" in CREATIVE_CSS
    import pymupdf
    from weasyprint import HTML

    from app.docgen.resume.theme_manager import get_theme_manager

    css = get_theme_manager().get_css("creative")
    full_html = (
        f"<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>{_body('creative')}</body></html>"
    )
    pdf_path = "/tmp/resume_audit/t_creative.pdf"
    HTML(string=full_html).write_pdf(pdf_path)
    doc = pymupdf.open(pdf_path)
    assert doc.page_count <= 3
    assert "星海科技" in doc[0].get_text()  # 第 1 页必须能看到最近经历
    doc.close()


def test_boss_zhipin_removes_page_counter_and_groups_skills():
    from app.docgen.resume.theme_css.boss_zhipin import BOSS_ZHIPIN_CSS

    assert "counter(page)" not in BOSS_ZHIPIN_CSS
    body = _body("boss_zhipin")
    assert '<div class="skill-row"><b>核心语言</b>：' in body


def test_linkedin_uses_english_section_titles():
    body = _body("linkedin")
    # 大写由 CSS text-transform 呈现，HTML 源码为 Title Case
    assert "Work Experience" in body
    assert "Skills" in body
    assert ">工作经历<" not in body


def test_bold_numbers_applied_in_legacy_bullets():
    body = _body("professional")
    assert "<b>30 万</b>" in body  # 摘要与 bullet 中的关键数字加粗


@pytest.mark.parametrize(
    "css_module",
    ["PROFESSIONAL_CSS", "CREATIVE_CSS", "MINIMAL_CSS"],
)
def test_cjk_font_fallback_first(css_module: str):
    import app.docgen.resume.theme_css as theme_css

    css = getattr(theme_css, css_module)
    assert "PingFang SC" in css
    assert css.index("PingFang SC") < css.index("Noto Sans SC")


def test_kami_metric_dividers_and_break_rules():
    from app.docgen.resume.kami_css import KAMI_CSS

    assert ".metric + .metric" in KAMI_CSS
    assert "break-after: avoid" in KAMI_CSS
