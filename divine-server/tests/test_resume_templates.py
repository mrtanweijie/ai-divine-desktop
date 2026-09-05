"""12 套简历模板库：渲染、双输出（可编辑/纯净 HTML + PDF）与工具链集成测试。"""

from pathlib import Path

import pytest

from app.docgen.resume.models import ResumeData
from app.docgen.resume.templates import build_html, render_template_resume
from app.docgen.resume.templates.registry import TEMPLATE_REGISTRY, TEMPLATE_IDS
from app.docgen.resume.sample_data import SAMPLE_RESUME

TEMPLATE_IDS_UNDER_TEST = [
    "tpl_professional",
    "tpl_modern",
    "tpl_minimal",
    "tpl_academic",
    "tpl_executive",
    "tpl_creative",
    "tpl_product",
    "tpl_data",
    "tpl_freshgrad",
    "tpl_lateral",
    "tpl_compact",
    "tpl_global",
    "creative",
    "minimal",
    "boss_zhipin",
    "finance",
    "linkedin",
    "kami",
    "kami_white",
]


def _sample_dict() -> dict:
    data = dict(SAMPLE_RESUME)
    data["certifications"] = ["AWS SAA", "CET-6"]
    data["languages"] = ["中文（母语）", "英语（CET-6，可工作语言）"]
    data["honors"] = ["2023：年度优秀员工", "2022：国家级奖项"]
    return data


def test_registry_unified_library():
    """统一模板库：12 套母版 + 7 套经典风格 = 19 套。"""
    assert len(TEMPLATE_IDS_UNDER_TEST) == 19
    assert set(TEMPLATE_IDS) == set(TEMPLATE_IDS_UNDER_TEST)
    for entry in TEMPLATE_REGISTRY.values():
        assert entry["display_name"] and entry["tip"]
        assert entry["industry_keywords"]


_LEGACY_IDS = {
    "creative",
    "minimal",
    "boss_zhipin",
    "finance",
    "linkedin",
    "kami",
    "kami_white",
}


@pytest.mark.parametrize("template_id", TEMPLATE_IDS_UNDER_TEST)
def test_build_html_editable_contains_content_and_toolbar(template_id: str):
    html = build_html(_sample_dict(), template_id, "single", editable=True)
    entry = TEMPLATE_REGISTRY[template_id]
    # 姓名、模板名与打印能力必须出现
    assert SAMPLE_RESUME["name"] in html
    assert entry["display_name"] in html
    assert "window.print()" in html
    assert "@page{size:A4" in html or "@page {" in html
    if template_id in _LEGACY_IDS:
        # 迁移自旧渲染器的 7 套：无 contenteditable 编辑态（静态 HTML + 工具条）
        assert ' contenteditable="true"' not in html
    else:
        assert html.count(' contenteditable="true"') >= 5


@pytest.mark.parametrize("template_id", TEMPLATE_IDS_UNDER_TEST)
def test_build_html_clean_strips_editing(template_id: str):
    clean = build_html(_sample_dict(), template_id, "single", editable=False)
    # 正文不含编辑属性与工具条（CSS 中的选择器与 .toolbar 规则允许保留）
    assert ' contenteditable="true"' not in clean
    assert '<div class="toolbar"' not in clean
    assert "window.print()" not in clean
    assert SAMPLE_RESUME["name"] in clean


def test_multi_layout_appends_multipage_print_css():
    single = build_html(_sample_dict(), "tpl_professional", "single", editable=False)
    multi = build_html(_sample_dict(), "tpl_professional", "multi", editable=False)
    assert "margin:10mm 0 11mm" in multi and "margin:10mm 0 11mm" not in single
    assert "break-inside:avoid" in multi
    # 双栏紧凑版多页打印时侧栏转通栏
    compact_multi = build_html(_sample_dict(), "tpl_compact", "multi", editable=False)
    assert ".page{display:block}.side{width:auto}" in compact_multi


def test_labeled_skills_split_into_kv_rows_without_pipe_leak():
    data = _sample_dict()
    data["skills"] = ["核心语言|Java 8 年", "数据库|MySQL 分库分表"]
    html = build_html(data, "tpl_professional", "single", editable=False)
    body = html.split("<body>", 1)[1]
    assert "核心语言" in body and "Java" in body
    assert "分库分表" in body
    # 竖线不应出现在正文文本中
    assert "核心语言|" not in body


def test_chip_item_prefers_label_with_title_hint():
    html = build_html(_sample_dict(), "tpl_modern", "single", editable=False)
    body = html.split("<body>", 1)[1]
    assert "核心语言</span>" in body
    assert "核心语言|Java" not in body


def test_template_specific_sections_render():
    data = _sample_dict()
    data.update(
        {
            "publications": [{"title": "Robust Learning", "venue": "ACL 2023", "year": "2023", "tags": "CCF-A"}],
            "works": [{"name": "品牌重塑", "result": "认知度 +19pt"}],
            "transferable": [{"source": "教研", "ability": "需求拆解", "description": "12 册教案", "mapping": "需求分层"}],
            "pivot": "从 <b>8 年教研</b>转型产品经理",
            "en_name": "YU CHEN",
            "en_title": "Senior Engineer",
        }
    )
    work = data["work"][0]
    work["en_company"] = "Xinghai Tech"
    work["en_points"] = ["Led migration"]
    resume = ResumeData.from_dict(data)
    assert "Robust Learning" in build_html(resume, "tpl_academic", "single", editable=False)
    assert "品牌重塑" in build_html(resume, "tpl_creative", "single", editable=False)
    lateral = build_html(resume, "tpl_lateral", "single", editable=False)
    assert "<b>8 年教研</b>" in lateral  # pivot 富文本允许加粗且不被转义泄露
    assert "&lt;b&gt;" not in lateral
    global_html = build_html(resume, "tpl_global", "single", editable=False)
    assert "YU CHEN" in global_html and "Xinghai Tech" in global_html


def test_render_template_resume_outputs(tmp_path: Path):
    output = tmp_path / "陈屿" / "简历.pdf"
    files = render_template_resume(
        _sample_dict(), str(output), "tpl_professional", "single", "both"
    )
    assert len(files) == 3
    pdf_path, html_path, clean_path = (Path(p) for p in files)
    assert pdf_path == output and pdf_path.stat().st_size > 1000
    assert html_path.suffix == ".html"
    assert ' contenteditable="true"' not in clean_path.read_text(encoding="utf-8")


def test_render_template_resume_html_only(tmp_path: Path):
    output = tmp_path / "简历.pdf"  # 不产出 PDF
    files = render_template_resume(
        _sample_dict(), str(output), "tpl_minimal", "single", "html"
    )
    assert len(files) == 2
    assert all(not p.endswith(".pdf") for p in files)


def test_string_actions_and_highlights_do_not_explode_into_chars():
    """回归：字符串型 actions/highlights 曾被逐字拆成单字 li（一列汉字）。"""
    data = _sample_dict()
    data["projects"] = [
        {
            "name": "数据集成平台",
            "role": "产品负责人",
            "actions": "接入流程重构、连接器市场、用量计费改造",
            "impact": "ARR 5,200 万",
        }
    ]
    data["work"] = [
        {
            "company": "某公司",
            "position": "产品经理",
            "period": "2021.05 - 至今",
            "points": "重构数据接入流程，首张报表时长由 9 天压缩至 4 小时",
        }
    ]
    resume = ResumeData.from_dict(data)
    # 归一化后必须是字符串列表，而非可迭代字符串
    assert resume.projects[0].highlights == ["接入流程重构、连接器市场、用量计费改造"]
    assert resume.experiences[0].highlights == [
        "重构数据接入流程，首张报表时长由 9 天压缩至 4 小时"
    ]
    for template_id in ("tpl_compact", "tpl_professional"):
        html = build_html(resume, template_id, "multi", editable=False)
        body = html.split("<body>", 1)[1]
        assert "<li>接</li>" not in body
        assert "接入流程重构、连接器市场、用量计费改造" in body


def test_unknown_template_raises_with_options():
    with pytest.raises(ValueError) as exc:
        build_html(_sample_dict(), "tpl_nonexistent", "single", editable=True)
    assert "tpl_professional" in str(exc.value)


def test_engine_suggests_template_by_industry():
    from app.docgen.pdf.engine import _suggest_resume_theme

    assert _suggest_resume_theme("帮我做一份应届生校招简历", {}) == "tpl_freshgrad"
    assert _suggest_resume_theme("我是产品经理想要一份简历", {}) == "tpl_product"
    assert _suggest_resume_theme("做一份中英双语简历，我要投外企", {}) == "tpl_global"
    # 无模板关键词时回落到旧主题映射
    assert _suggest_resume_theme("简历，投 boss 直聘", {}) == "boss_zhipin"
