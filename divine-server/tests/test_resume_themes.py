"""统一模板库（templates/，19 套）渲染回归：竖线泄漏、假百分比、跨页与断页规则。"""

import pytest

from app.docgen.resume.models import ResumeData
from app.docgen.resume.sample_data import SAMPLE_RESUME
from app.docgen.resume.templates import build_html, registry, render_template_resume
from app.docgen.resume.templates.registry import TEMPLATE_REGISTRY, TEMPLATE_IDS

THEME_IDS = [
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


def _body(template_id: str) -> str:
    resume = ResumeData.from_dict(SAMPLE_RESUME)
    return build_html(resume, template_id, "single", editable=False)


def test_registry_unifies_all_templates():
    """新旧模板统一注册：12 套母版 + 7 套经典风格 = 19 套，professional 已删除。"""
    assert len(TEMPLATE_IDS) == 19
    assert set(TEMPLATE_IDS) == set(THEME_IDS)
    assert "professional" not in TEMPLATE_REGISTRY  # 无对应风格的旧主题已删除
    for entry in TEMPLATE_REGISTRY.values():
        assert entry["display_name"] and entry["tip"]
        assert entry["industry_keywords"]


def test_skill_pairs_and_plain_splits_labeled_lines():
    from app.docgen.resume.templates.helpers import skill_pairs_and_plain

    resume = ResumeData.from_dict(SAMPLE_RESUME)
    pairs, plain = skill_pairs_and_plain(resume)
    assert pairs and pairs[0][0] == "核心语言"
    assert "|" not in pairs[0][1]
    assert plain == []


def _pairs(resume):
    from app.docgen.resume.templates.helpers import skill_pairs_and_plain

    return skill_pairs_and_plain(resume)


def test_skill_pairs_and_plain_falls_back_to_core_skills():
    from app.docgen.resume.templates.helpers import skill_pairs_and_plain

    resume = ResumeData.from_dict({"name": "测试", "core_skills": ["Python", "SQL"]})
    pairs, plain = skill_pairs_and_plain(resume)
    assert pairs == [] and plain == ["Python", "SQL"]


@pytest.mark.parametrize("template_id", THEME_IDS)
def test_no_pipe_leak_in_rendered_html(template_id: str):
    body = _body(template_id)
    assert "核心语言|" not in body
    assert "后端框架|" not in body


@pytest.mark.parametrize("template_id", ["tpl_creative", "creative"])
def test_no_fabricated_skill_percentage(template_id: str):
    body = _body(template_id)
    assert "80%" not in body


def test_creative_paginates_without_blank_first_page():
    """回归：flex 双栏曾整体被搬到第 2 页导致首页大面积空白（已改 table-cell）。"""
    from app.docgen.resume.templates import t13_creative

    assert "display: table" in t13_creative.CSS
    import pymupdf
    from weasyprint import HTML

    resume = ResumeData.from_dict(SAMPLE_RESUME)
    files = render_template_resume(
        SAMPLE_RESUME, "/tmp/resume_audit/t_creative.pdf", "creative", "single", "pdf"
    )
    doc = pymupdf.open(files[0])
    assert doc.page_count <= 3
    assert resume.name in doc[0].get_text()
    doc.close()


def test_boss_zhipin_removes_page_counter_and_groups_skills():
    from app.docgen.resume.templates import t15_boss_zhipin

    assert "counter(page)" not in t15_boss_zhipin.CSS
    body = _body("boss_zhipin")
    assert '<div class="skill-row"><b>核心语言</b>：' in body


def test_linkedin_uses_english_section_titles():
    body = _body("linkedin")
    # 大写由 CSS text-transform 呈现，HTML 源码为 Title Case
    assert "Work Experience" in body
    assert "Skills" in body
    assert ">工作经历<" not in body


def test_bold_numbers_applied_in_bullets():
    body = _body("tpl_professional")
    assert "<b>30 万</b>" in body  # 摘要与 bullet 中的关键数字加粗


@pytest.mark.parametrize(
    "module_name",
    ["t13_creative", "t14_minimal", "t15_boss_zhipin"],
)
def test_cjk_font_fallback_present(module_name: str):
    import app.docgen.resume.templates as tpl_pkg

    css = getattr(tpl_pkg, module_name).CSS
    assert "PingFang SC" in css or "Microsoft YaHei" in css


def test_kami_metric_dividers_and_break_rules():
    from app.docgen.resume.templates import t18_kami

    assert ".metric + .metric" in t18_kami.CSS
    assert "break-after: avoid" in t18_kami.CSS


def test_string_skills_do_not_explode_into_char_chips():
    """回归：skills 被当成长字符串逐字迭代，每个字符变成一个 chip（一屏单字胶囊），
    且巨型 flex chips 容器不可跨页，把首页挤出大片空白。"""
    data = {
        "name": "测",
        "skills": "框架|React（Redux/Zustand）· Vue3\n语言|TypeScript · JavaScript",
    }
    resume = ResumeData.from_dict(data)
    assert len(resume.skills) == 2
    assert resume.skills[0].name == "框架|React（Redux/Zustand）· Vue3"
    html = build_html(resume, "tpl_modern", "single", editable=False)
    body = html.split("<body>", 1)[1]
    assert ">框<" not in body and ">R<" not in body  # 没有逐字 chip
    assert "框架" in body


def test_nested_projects_in_work_are_rendered():
    """回归：work[].projects 曾被非 kami 模板整体丢弃（用户 10 个项目"没看到项目模块"）。"""
    data = {
        "name": "李铭",
        "title": "资深前端工程师",
        "contact": {"email": "a@b.c"},
        "work": [
            {
                "company": "某券商",
                "position": "前端负责人",
                "period": "2019 - 至今",
                "projects": [
                    {
                        "name": "机构级实时行情交易工作台",
                        "summary": "服务 500 家机构客户",
                        "points": ["行情延迟 P99 降至 80ms"],
                    },
                    {"name": "智能风控运营中台", "points": ["风控处置效率提升 3 倍"]},
                ],
            }
        ],
    }
    resume = ResumeData.from_dict(data)
    assert resume.experiences[0].projects  # 归一化保留嵌套项目
    for template_id in ("tpl_professional", "tpl_modern", "finance"):
        html = build_html(resume, template_id, "single", editable=False)
        body = html.split("<body>", 1)[1]
        assert "机构级实时行情交易工作台" in body, f"{template_id} 丢失嵌套项目"
        assert "智能风控运营中台" in body
        assert "行情延迟" in body and "降至" in body  # 数字会被加粗拆开，验证文案主体


def test_projects_are_separate_section_not_inline_in_experience():
    """母版约定【职业经历】与【项目】分开：work[].projects 并入"项目"独立板块
    （ResumeData.merged_projects），不再混排进经历 bullet；无项目时不渲染空板块。"""
    data = {
        "name": "李铭",
        "title": "资深前端工程师",
        "work": [
            {
                "company": "某券商",
                "position": "前端负责人",
                "period": "2019 - 至今",
                "highlights": ["负责交易工作台前端架构与技术治理"],
                "projects": [
                    {
                        "name": "机构级实时行情交易工作台",
                        "summary": "服务 500 家机构客户",
                        "points": ["行情延迟 P99 降至 80ms"],
                    }
                ],
            }
        ],
    }
    resume = ResumeData.from_dict(data)
    html = build_html(resume, "tpl_professional", "single", editable=False)
    body = html.split("<body>", 1)[1]
    i_exp = body.find("职业经历")
    i_proj = body.find("项目经历")
    assert 0 <= i_exp < i_proj, (i_exp, i_proj)  # 经历板块在项目板块之前
    assert "机构级实时行情交易工作台" in body[i_proj:]  # 项目落入独立板块
    assert '<li class="lead">' not in body[:i_proj]  # 经历 bullet 不再内嵌项目导语

    # 项目板块非必须：无项目时不渲染空标题
    no_proj = ResumeData.from_dict(
        {"name": "张三", "title": "工程师",
         "work": [{"company": "A", "title": "工程师", "highlights": ["成果 x"]}]}
    )
    html_no = build_html(no_proj, "tpl_professional", "single", editable=False)
    assert "项目经历" not in html_no


def test_no_zero_width_ghost_artifacts():
    """回归：content:"" 空伪元素会发射零宽填充矩形（空文本行框），
    在部分 PDF 查看器中显示为标题旁的发丝竖线。空伪元素统一带 font-size:0。"""
    import pymupdf
    from weasyprint import HTML

    resume = ResumeData.from_dict(SAMPLE_RESUME)
    for template_id in ("tpl_freshgrad", "tpl_modern", "tpl_executive"):
        html = build_html(resume, template_id, "single", editable=False)
        pdf_path = f"/tmp/resume_audit/t_ghost_{template_id}.pdf"
        HTML(string=html).write_pdf(pdf_path)
        doc = pymupdf.open(pdf_path)
        ghosts = [
            d
            for d in doc[0].get_drawings()
            if (d["rect"].x1 - d["rect"].x0) < 0.01
            and (d["rect"].y1 - d["rect"].y0) > 1
        ]
        assert ghosts == [], f"{template_id} 存在 {len(ghosts)} 个零宽伪影: {ghosts[:2]}"
        doc.close()


def test_professional_heavy_content_keeps_main_column_on_every_page():
    """回归：双栏若用 flex，WeasyPrint 无法分割容器，内容超页时主栏整体
    被搬到最后一页（前几页只有侧栏）。table-cell 布局跨页正常。"""
    import pymupdf
    from weasyprint import HTML

    from app.docgen.resume.templates import t13_creative

    heavy = {
        "name": "木木",
        "title": "资深前端开发工程师",
        "contact": {"email": "a@b.c", "phone": "138-0000-0000"},
        "summary": "10 年前端开发经验。" * 3,
        "work": [
            {
                "company": f"公司{i}",
                "position": "前端负责人",
                "period": f"20{16 + i} - 20{17 + i}",
                "points": [f"主导项目{i}-{j}：" + "成果描述" * 30 for j in range(4)],
            }
            for i in range(6)
        ],
        "education": [{"school": "某大学", "degree": "本科", "period": "2012 - 2016"}],
    }
    resume = ResumeData.from_dict(heavy)
    html = build_html(resume, "creative", "single", editable=False)
    pdf_path = "/tmp/resume_audit/t_creative_heavy.pdf"
    HTML(string=html).write_pdf(pdf_path)
    doc = pymupdf.open(pdf_path)
    assert doc.page_count >= 2  # 内容确实跨页
    for page in doc:
        main_text = page.get_text(
            "text",
            clip=pymupdf.Rect(220, 0, page.rect.width, page.rect.height),
        ).strip()
        assert main_text, "每一页的主栏都必须有正文（主栏不得被整体搬到末页）"
    doc.close()
