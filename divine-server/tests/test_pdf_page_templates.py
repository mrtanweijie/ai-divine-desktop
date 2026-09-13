"""论文/报告四套页式模板：主题注册、骨架提取、配方分流与端到端渲染。

四套模板（academic_report / thesis_paper / data_report / research_report）与 travel
同一管线：CSS 从模板 <style> 提取，LLM 按骨架产出 HTML body，模板自带封面与页眉页脚。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app.docgen.pdf.cover_builder import build_html_template_document
from app.docgen.pdf.design_rules import (
    INDEPENDENT_THEME_RECIPES,
    PAGE_TEMPLATE_THEMES,
    resolve_design,
    resolve_family_theme,
)
from app.docgen.pdf.engine import PDFTool
from app.docgen.pdf.recipes import (
    PAGE_TEMPLATE_RECIPES,
    detect_recipe,
    get_recipe,
)
from app.docgen.pdf.theme_registry import (
    THEMES,
    html_template_pages,
    html_template_skeleton,
    is_html_template_theme,
    load_theme_css,
    theme_owns_cover,
)

# 每套模板的固定页数（页式模板页数不可增减）
EXPECTED_PAGES = {
    "academic_report": 4,
    "thesis_paper": 3,
    "data_report": 4,
    "research_report": 4,
}


class StructuredLLM:
    """模拟「按模板骨架正确产出 HTML body」的模型。

    意图阶段返回 JSON，内容阶段返回配方自带的降级内容（结构与模板一致），
    从而在零 API 成本下跑通完整链路。
    """

    def __init__(self, recipe) -> None:
        self.recipe = recipe

    async def stream(self, messages, tools=None, think=False):  # noqa: ANN001, ANN202
        system_prompt = messages[0].get("content", "") if messages else ""
        if "规划器" in system_prompt:
            yield {
                "type": "message",
                "content": '{"title": "测试标题", "topic": "测试主题", "sections": []}',
            }
            return
        intent = self.recipe.fallback_intent("测试主题")
        yield {"type": "message", "content": self.recipe.fallback_content(intent)}


# ---------------------------------------------------------------------------
# 主题注册与 CSS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("theme", sorted(PAGE_TEMPLATE_THEMES))
def test_theme_registered_as_html_template(theme: str):
    assert theme in THEMES
    assert is_html_template_theme(theme)
    assert theme_owns_cover(theme), "四套模板自带封面页"
    assert THEMES[theme]["file"].endswith(".html")
    assert THEMES[theme]["display_name"]
    assert THEMES[theme]["description"]


@pytest.mark.parametrize("theme", sorted(PAGE_TEMPLATE_THEMES))
def test_css_extracted_from_template_without_module_styles(theme: str):
    css = load_theme_css(theme)
    # 页式模板自带完整样式，不叠加布局模块样式
    assert ".hero-stat" not in css
    assert ".conclusion-box" not in css
    # 模板自身的选择器应当在
    assert ".page" in css
    # 管线注入的 :root 覆盖块含主色变量
    assert "--primary" in css


def test_template_primary_alias_wired_to_theme_token():
    """模板里的语义色别名必须挂在 --primary 上，否则 theme_colors 覆盖会失效。"""
    aliases = {
        "academic_report": ("--navy: var(--primary)", "--blue-soft: var(--primary-light)"),
        "data_report": ("--blue: var(--primary)", "--blue-deep: var(--primary-dark)"),
        "research_report": (
            "--green: var(--primary)",
            "--green-deep: var(--primary-dark)",
        ),
    }
    for theme, tokens in aliases.items():
        css = load_theme_css(theme)
        for token in tokens:
            assert token in css, f"{theme} 缺少别名声明：{token}"
    # 单色主题（论文）的主色即标题与表格线色，直接是字面量
    assert "--primary: #1A1A1A" in load_theme_css("thesis_paper")


def test_primary_override_reaches_rendered_css():
    css = load_theme_css("data_report", overrides={"--primary": "#B03A2E"})
    # 注入块在后，覆盖模板 :root 的同名声明
    assert css.rindex("--primary: #B03A2E") > css.index("--primary: #14497B")


# ---------------------------------------------------------------------------
# 骨架提取
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("theme,expected", sorted(EXPECTED_PAGES.items()))
def test_skeleton_keeps_every_page(theme: str, expected: int):
    skeleton = html_template_skeleton(theme)
    # 骨架 = 说明行 + 设计注释 + 全部页片段；用权威取页函数核对页数
    pages = html_template_pages(theme)
    assert len(pages) == expected, f"{theme} 页数不符：{len(pages)} ≠ {expected}"
    for page in pages:
        opening = page.lstrip().split(">", 1)[0] + ">"
        assert opening in skeleton, f"{theme} 骨架缺少页片段：{opening}"
    assert "<style" not in skeleton, "骨架不应含样式块"
    assert "{{" in skeleton, "骨架应保留占位符供 LLM 替换"


def test_pages_helper_excludes_page_head():
    """研报模板的 .page-head 不能被误判为页边界。"""
    pages = html_template_pages("research_report")
    assert len(pages) == EXPECTED_PAGES["research_report"]
    for page in pages:
        assert not page.lstrip().startswith('<div class="page-head"')


def test_fallback_content_has_no_visible_comment_text():
    """降级内容不能把模板头部的设计说明注释当正文输出。"""
    recipe = get_recipe("data_report")
    content = recipe.fallback_content(recipe.fallback_intent("测试"))
    assert "【设计语言】" not in content
    assert "渲染兼容" not in content
    assert "{{" not in content and "}}" not in content
    assert len(re.findall(r'<div class="page(?:"|\s)', content)) == 4


# ---------------------------------------------------------------------------
# 配方分流
# ---------------------------------------------------------------------------

def test_recipes_registered():
    assert PAGE_TEMPLATE_RECIPES <= set(__import__(
        "app.docgen.pdf.recipes", fromlist=["RECIPE_REGISTRY"]
    ).RECIPE_REGISTRY)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("写一篇深度学习方向的论文", "thesis_paper"),
        ("帮我写毕业论文", "thesis_paper"),
        ("做一份课程学术报告", "academic_report"),
        ("写个开题报告", "academic_report"),
        ("帮我写一份经营数据分析报告", "data_report"),
        ("出一份行业研究报告", "research_report"),
        ("做份白皮书", "research_report"),
        # 不能被更宽泛的 report/business 吸走
        ("帮我写份周报", "report"),
        ("做一份商业分析报告", "business"),
    ],
)
def test_detect_recipe_routing(text: str, expected: str):
    assert detect_recipe(text) == expected


def test_independent_recipes_declared():
    assert PAGE_TEMPLATE_RECIPES <= INDEPENDENT_THEME_RECIPES


@pytest.mark.parametrize("recipe_name", sorted(PAGE_TEMPLATE_RECIPES))
def test_resolve_design_keeps_recipe_theme(recipe_name: str):
    """场景词（如“行业”）不得把四套模板的主题带偏。"""
    recipe = get_recipe(recipe_name)
    decision = resolve_design(
        "行业深度分析报告，客户提案，要封面和目录",
        recipe_name=recipe_name,
        recipe_theme=recipe.css_template,
        recipe_color=recipe.color_scheme,
    )
    assert decision.theme == recipe.css_template
    assert decision.scene is None


def test_family_theme_guard():
    # 论文配方不接受 travel 主题
    assert resolve_family_theme("travel_swiss", "data_report") == "data_report"
    # 论文配方不接受别家模板主题（一个配方对一个模板）
    assert resolve_family_theme("thesis_paper", "data_report") == "data_report"
    # 旅行配方接受同族主题
    assert resolve_family_theme("travel_bento", "travel") == "travel_bento"


def test_markdown_path_rejects_page_template_theme():
    """页式模板主题不能落到 markdown 渲染路径上。"""
    decision = resolve_design(
        "写一份报告",
        recipe_name="report",
        theme="data_report",
        recipe_theme="universal",
        recipe_color="blue",
    )
    assert decision.theme == "universal"


def test_theme_param_equivalent_to_kind():
    """theme 传四套之一时等价于传同名 kind。"""
    tool = PDFTool()
    recipe = get_recipe("data_report")
    result = asyncio.run(
        tool.run(
            prompt="测试",
            output=Path("/tmp") / "theme_as_kind.pdf",
            theme="data_report",
            llm=StructuredLLM(recipe),
        )
    )
    assert result["recipe"] == "data_report"


# ---------------------------------------------------------------------------
# 文档组装
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("theme", sorted(PAGE_TEMPLATE_THEMES))
def test_document_skips_system_cover_and_header(theme: str):
    pages = "\n".join(html_template_pages(theme))
    document = build_html_template_document(pages, "标题", theme=theme)
    # 模板自带封面，系统不再造封面，也不注入 .header 标题条
    assert '<div class="header">' not in document
    assert "cover-page" not in document


def test_travel_still_gets_header_and_cover():
    """回归保护：travel 主题仍由系统造封面并注入 .header。"""
    document = build_html_template_document(
        '<div class="page">x</div>', "标题", theme="travel"
    )
    assert '<div class="header">' in document


# ---------------------------------------------------------------------------
# 端到端渲染
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,expected", sorted(EXPECTED_PAGES.items()))
def test_expected_pages_matches_template(kind: str, expected: int):
    assert get_recipe(kind).expected_pages == expected


# ---------------------------------------------------------------------------
# data_report 条形图色阶跟随主色
# ---------------------------------------------------------------------------

# 原设计色板（模板里的字面量兜底值）
_BAR_DEFAULT = [(20, 73, 123), (61, 116, 168), (109, 156, 199), (168, 195, 220)]


def _bar_colors(path: Path) -> list[tuple[int, int, int]]:
    """抽取 PDF 里的条形填充色（.chart-bar 高度 12px ≈ 9pt）。"""
    import pymupdf

    found: list[tuple[int, int, int]] = []
    for page in pymupdf.open(path):
        for draw in page.get_drawings():
            fill = draw.get("fill")
            rect = draw["rect"]
            if fill and 7.5 < rect.height < 10.5 and rect.width > 20:
                found.append(tuple(round(channel * 255) for channel in fill))
    return found


def test_bar_ramp_derived_from_primary():
    from app.docgen.pdf.theme_colors import derive_bar_ramp

    ramp = derive_bar_ramp("#B03A2E")
    assert sorted(ramp) == ["--bar-1", "--bar-2", "--bar-3", "--bar-4"]
    # 首级即主色本身
    assert ramp["--bar-1"].lower() == "#b03a2e"
    # 逐级变亮（亮度阶梯）
    def lum(hex_value: str) -> int:
        return sum(int(hex_value[i : i + 2], 16) for i in (1, 3, 5))

    levels = [lum(ramp[f"--bar-{i}"]) for i in range(1, 5)]
    assert levels == sorted(levels), f"色阶未逐级变亮：{levels}"
    assert derive_bar_ramp("不是颜色") == {}


def test_data_report_keeps_default_bar_palette():
    """无主色覆盖时保留模板字面量色板，派生色不得改动默认观感。"""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pymupdf")
    from app.llm import MockLLM

    out = _tmp_out("bar_default")
    asyncio.run(
        PDFTool().run(
            prompt="测试", output=out, kind="data_report", llm=MockLLM()
        )
    )
    colors = set(_bar_colors(out))
    assert colors, "未抽取到任何条形"
    assert colors <= set(_BAR_DEFAULT), f"出现非原色板的条形色：{colors - set(_BAR_DEFAULT)}"
    assert len(colors) == 4, f"色阶级数不对：{colors}"


def test_data_report_bar_ramp_follows_primary():
    """主色被覆盖后，条形图 4 级色阶必须整体跟随，不得残留原蓝色。"""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pymupdf")
    from app.docgen.pdf.theme_colors import derive_bar_ramp
    from app.llm import MockLLM

    primary = "#B03A2E"
    out = _tmp_out("bar_recolor")
    asyncio.run(
        PDFTool().run(
            prompt="测试",
            output=out,
            kind="data_report",
            llm=MockLLM(),
            color_overrides={"--primary": primary},
        )
    )
    colors = set(_bar_colors(out))
    assert colors, "未抽取到任何条形"
    ramp = derive_bar_ramp(primary)
    expected = {
        tuple(int(ramp[f"--bar-{i}"][j : j + 2], 16) for j in (1, 3, 5))
        for i in range(1, 5)
    }
    assert colors == expected, f"条形色未跟随主色：实际 {colors} / 期望 {expected}"
    # 关键回归点：不得残留蓝色（蓝分量明显大于红分量）
    assert not [c for c in colors if c[2] > c[0] + 30], f"残留蓝色条：{colors}"


# ---------------------------------------------------------------------------
# research_report 二级浅色（引用块底色）跟随主色
# ---------------------------------------------------------------------------

_FAINT_DEFAULT = (244, 248, 246)  # 原设计 --green-faint #F4F8F6


def _quote_bg(path: Path) -> set[tuple[int, int, int]]:
    """抽取引用块（.pull-quote）的大面积极浅底色。"""
    import pymupdf

    found = set()
    for page in pymupdf.open(path):
        for draw in page.get_drawings():
            fill = draw.get("fill")
            rect = draw["rect"]
            if fill and rect.width > 300 and rect.height > 30:
                color = tuple(round(c * 255) for c in fill)
                if min(color) > 200 and color != (255, 255, 255):
                    found.add(color)
    return found


def test_faint_tint_derived_from_primary():
    from app.docgen.pdf.theme_colors import derive_faint_tint

    for primary in ("#1E5145", "#B03A2E"):
        out = derive_faint_tint(primary)
        assert list(out) == ["--primary-faint"]
        # 极浅：三通道都很高
        rgb = tuple(int(out["--primary-faint"][i : i + 2], 16) for i in (1, 3, 5))
        assert min(rgb) > 200, f"{primary} 派生出的浅色不够浅：{rgb}"
    assert derive_faint_tint("不是颜色") == {}


def test_research_report_keeps_original_two_tints():
    """无覆盖时还原原设计的两个浅色层次（soft 与 faint 不应相同）。"""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pymupdf")
    from app.llm import MockLLM

    out = _tmp_out("faint_default")
    asyncio.run(
        PDFTool().run(
            prompt="测试", output=out, kind="research_report", llm=MockLLM()
        )
    )
    assert _FAINT_DEFAULT in _quote_bg(out), "引用块未使用原设计的 --green-faint"


def test_research_report_faint_tint_follows_primary():
    """主色被覆盖后，引用块底色必须跟随，不得残留原绿色的浅底。"""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pymupdf")
    from app.docgen.pdf.theme_colors import derive_faint_tint
    from app.llm import MockLLM

    primary = "#B03A2E"
    out = _tmp_out("faint_recolor")
    asyncio.run(
        PDFTool().run(
            prompt="测试",
            output=out,
            kind="research_report",
            llm=MockLLM(),
            color_overrides={"--primary": primary},
        )
    )
    expected_hex = derive_faint_tint(primary)["--primary-faint"]
    expected = tuple(int(expected_hex[i : i + 2], 16) for i in (1, 3, 5))
    bgs = _quote_bg(out)
    assert expected in bgs, f"引用块底色未跟随主色：实际 {bgs} / 期望含 {expected}"
    # 关键回归点：不得残留原设计的绿色浅底
    assert _FAINT_DEFAULT not in bgs, "残留原绿色浅底"


def _tmp_out(name: str) -> Path:
    """把测试产物写到 /tmp（沙箱下 tmp_path 建子目录会被权限代理拒绝）。"""
    path = Path("/tmp") / f"pdf_tpl_{name}.pdf"
    path.unlink(missing_ok=True)
    return path


# ---------------------------------------------------------------------------
# 样张占位符卫生（011–016 全量）
# ---------------------------------------------------------------------------

# 011–014 是 PDF 管线的页式模板，占位符必须扁平；
# 015–016 是 PPT 主题（keynote/devconf）的视觉样张，历史上用「整句包裹 + 内层插槽」的
# 嵌套写法，只要求括号平衡——若日后把它们接入会做占位符替换的管线，必须先扁平化。
_ALL_SAMPLES = {
    "011-academic-report-template-20260912.html",
    "012-thesis-paper-template-20260912.html",
    "013-data-analysis-report-template-20260912.html",
    "014-research-report-template-20260912.html",
    "015-launch-keynote-style-20260912.html",
    "016-product-intro-devconf-style-20260912.html",
}
_FLAT_REQUIRED = {
    "011-academic-report-template-20260912.html",
    "012-thesis-paper-template-20260912.html",
    "013-data-analysis-report-template-20260912.html",
    "014-research-report-template-20260912.html",
}


def _sample_lines(name: str) -> list[str]:
    """取样张正文行（跳过说明扁平约定的注释行，它本身就是反例）。"""
    text = (_doc_samples_dir() / name).read_text(encoding="utf-8")
    return [
        line
        for line in text.splitlines()
        if "扁平书写，禁止嵌套" not in line
    ]


@pytest.mark.parametrize("name", sorted(_ALL_SAMPLES))
def test_sample_placeholders_balanced(name: str):
    """占位符括号必须成对，且不得出现四重括号。

    011–016 里曾发现 4 处真实缺陷（015 一处漏闭合、016 一处四重括号 + 两处漏闭合）。
    """
    if not (_doc_samples_dir() / name).exists():
        pytest.skip(f"样张不存在：{name}")
    for lineno, line in enumerate(_sample_lines(name), 1):
        if "{{" not in line:
            continue
        assert line.count("{{") == line.count("}}"), (
            f"{name}:{lineno} 括号不平衡（开 {line.count('{{')} / 闭 {line.count('}}')}）："
            f"{line.strip()[:90]}"
        )
        assert "{{{{" not in line, f"{name}:{lineno} 出现四重括号：{line.strip()[:90]}"


@pytest.mark.parametrize("name", sorted(_FLAT_REQUIRED))
def test_pdf_sample_placeholders_are_flat(name: str):
    """接入 PDF 管线的四套样张：占位符必须扁平不嵌套。"""
    if not (_doc_samples_dir() / name).exists():
        pytest.skip(f"样张不存在：{name}")
    for lineno, line in enumerate(_sample_lines(name), 1):
        if "{{" not in line:
            continue
        # 去掉所有合法占位符后不应再有 {{ 残留（残留即嵌套）
        residue = re.sub(r"\{\{[^{}]*\}\}", "", line)
        assert "{{" not in residue, (
            f"{name}:{lineno} 占位符嵌套：{line.strip()[:90]}"
        )


# ---------------------------------------------------------------------------
# 提示词公共片段：收敛后必须保持各配方原有措辞（travel 提示词长期调过）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "theme,expected_desc",
    [
        ("travel", "完整旅行攻略"),
        ("travel_swiss", "现代风格旅行攻略"),
    ],
)
def test_travel_prompt_keeps_original_wording(theme: str, expected_desc: str):
    """travel 提示词必须保持原措辞（含空格）。

    `_skeleton_prompt` 收敛公共片段时曾拼出「PDF 的 完整旅行攻略」这种多余空格，
    这条测试锁住该不变量：以后改公共片段必须显式确认对 travel 的影响。
    """
    from app.docgen.pdf.base import PDFIntent
    from app.docgen.pdf.recipes import TravelRecipe

    recipe = TravelRecipe()
    intent = PDFIntent(
        title="T",
        topic="测试主题",
        style="travel",
        color_scheme="teal",
        meta={"theme": theme, "recipe": "travel"},
    )
    prompt = recipe.content_system_prompt(intent)
    assert prompt.startswith(
        "你是资深旅行手册作者。严格按下述【模板骨架】的页面结构与 CSS 类名，"
    )
    # 关键：不能出现「的 完整旅行攻略」这种多余空格
    assert f"输出一份可直接打印为 PDF 的{expected_desc} HTML body。" in prompt
    assert f"PDF 的 {expected_desc}" not in prompt
    assert "══════════════ 模板骨架（" in prompt
    assert "\n══════════════ 输出规则 ══════════════\n" in prompt


@pytest.mark.parametrize("kind", sorted(EXPECTED_PAGES))
def test_page_template_prompt_wording(kind: str):
    """四套论文/报告提示词的措辞与骨架块。"""
    recipe = get_recipe(kind)
    prompt = recipe.content_system_prompt(recipe.fallback_intent("测试主题"))
    assert prompt.startswith(
        f"你是资深{recipe.display_name}撰稿人。严格按下述【模板骨架】的页面结构与 CSS 类名，"
    )
    # desc 为空：不能拼成「PDF 的 」双空格或「PDF 的HTML」
    assert "输出一份可直接打印为 PDF 的 HTML body。" in prompt
    assert "PDF 的  " not in prompt and "PDF 的HTML" not in prompt
    assert f"模板骨架（{THEMES[kind]['file']}）" in prompt
    assert html_template_skeleton(kind) in prompt
    # 排版契约必须进提示词
    assert recipe.page_plan in prompt and recipe.extra_rules in prompt


# ---------------------------------------------------------------------------
# 样张（docs/templates）与运行时副本（pdf_themes）一致性
# ---------------------------------------------------------------------------

# docs/templates 编号文件 ↔ app/docgen/pdf/pdf_themes 运行时副本
_DOC_TO_RUNTIME = {
    "011-academic-report-template-20260912.html": "academic_report.html",
    "012-thesis-paper-template-20260912.html": "thesis_paper.html",
    "013-data-analysis-report-template-20260912.html": "data_report.html",
    "014-research-report-template-20260912.html": "research_report.html",
}


def _doc_samples_dir() -> Path:
    """仓库根下的 docs/templates（tests/ 在 divine-server 下，向上两级）。"""
    return Path(__file__).resolve().parents[2] / "docs" / "templates"


@pytest.mark.parametrize("doc_name,runtime_name", sorted(_DOC_TO_RUNTIME.items()))
def test_doc_sample_matches_runtime_copy(doc_name: str, runtime_name: str):
    """样张与 pdf_themes 副本必须逐行一致（忽略编辑器注入的属性）。

    二者先前已出现过「运行时副本有主色接线、样张没有」的漂移；这条测试把
    「改样张后同步复制」这个手工步骤变成可校验的约束。
    """
    doc_path = _doc_samples_dir() / doc_name
    runtime_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "docgen"
        / "pdf"
        / "pdf_themes"
        / runtime_name
    )
    if not doc_path.exists():
        pytest.skip(f"样张不存在（可能未随仓库分发）：{doc_name}")

    def normalized(path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8")
        # 外部页面编辑器会注入 data-page-node-id，不参与比对
        return [
            line
            for line in re.sub(r'\s+data-page-node-id="[^"]*"', "", text).splitlines()
            if line.strip()
        ]

    doc_lines, runtime_lines = normalized(doc_path), normalized(runtime_path)
    diff = [
        line
        for line in __import__("difflib").unified_diff(
            doc_lines, runtime_lines, lineterm="", n=0
        )
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not diff, (
        f"{doc_name} 与 {runtime_name} 不一致（{len(diff)} 处）。"
        "改完样张请同步复制到 app/docgen/pdf/pdf_themes/：\n"
        + "\n".join(d[:120] for d in diff[:10])
    )


class PatchLLM:
    """补页用假模型：记录每次请求，返回固定的续写内容。"""

    def __init__(self, patch: str) -> None:
        self.patch = patch
        self.requests: list[str] = []

    async def stream(self, messages, tools=None, think=False):  # noqa: ANN001, ANN202
        self.requests.append(messages[-1].get("content", "") if messages else "")
        yield {"type": "message", "content": self.patch}


def _count_pages(text: str) -> int:
    return len(re.findall(r'<div class="page(?:"|\s)', text))


def test_page_repair_appends_missing_pages():
    """生成被截断（页数不足）时，应接着已有页续写缺失页。"""
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("data_report")  # 4 页
    intent = recipe.fallback_intent("测试")
    pages = html_template_pages("data_report")
    truncated = "\n".join(pages[:2])

    llm = PatchLLM("\n".join(pages[2:]))
    out = asyncio.run(
        ensure_page_template_pages(truncated, intent, recipe, llm)
    )
    assert _count_pages(out) == 4
    # 首尾内容都在（不是重生成，而是接着补）
    assert "1,284" in out and "核心结论" in out
    # 续写提示必须点明缺失页数，否则模型无从定位
    assert "只补缺失的后 2 页" in llm.requests[0]


def test_page_repair_rejects_wrong_patch_count():
    """补出来的页数不对就放弃拼接，宁缺勿错。"""
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("data_report")
    intent = recipe.fallback_intent("测试")
    pages = html_template_pages("data_report")
    truncated = "\n".join(pages[:2])

    llm = PatchLLM(pages[2])  # 只补了 1 页，缺 2 页
    out = asyncio.run(
        ensure_page_template_pages(truncated, intent, recipe, llm)
    )
    assert _count_pages(out) == 2
    assert (intent.meta.get("content_qa") or {}).get("page_repair") == "rejected"


def test_page_repair_rejects_patch_containing_cover():
    """补页里混进封面页会打乱页序，必须拒绝。"""
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("data_report")
    intent = recipe.fallback_intent("测试")
    pages = html_template_pages("data_report")
    llm = PatchLLM(pages[2] + pages[0])  # 含封面页
    out = asyncio.run(
        ensure_page_template_pages("\n".join(pages[:2]), intent, recipe, llm)
    )
    assert _count_pages(out) == 2


def test_page_repair_noop_when_complete():
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("data_report")
    intent = recipe.fallback_intent("测试")
    full = "\n".join(html_template_pages("data_report"))
    llm = PatchLLM(full)
    out = asyncio.run(ensure_page_template_pages(full, intent, recipe, llm))
    assert _count_pages(out) == 4
    assert llm.requests == [], "页数已足时不应发起补页请求"


def test_page_repair_drops_incomplete_tail():
    """截断残留（未闭合标签）不能把补页嵌进残页内部。"""
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("data_report")
    intent = recipe.fallback_intent("测试")
    pages = html_template_pages("data_report")
    broken = pages[0] + '<div class="page"><p>未闭合的内容'  # 第 2 页没闭合
    llm = PatchLLM("\n".join(pages[1:]))
    out = asyncio.run(ensure_page_template_pages(broken, intent, recipe, llm))
    assert _count_pages(out) == 4
    assert "未闭合的内容" not in out


def test_page_repair_noop_for_travel():
    """travel 页数是天数相关的，没有 expected_pages，必须 no-op。"""
    from app.docgen.pdf.content import ensure_page_template_pages

    recipe = get_recipe("travel")
    intent = recipe.fallback_intent("测试")
    llm = PatchLLM("<div class=\"page\">patch</div>")
    src = '<div class="page">only one</div>'
    assert asyncio.run(ensure_page_template_pages(src, intent, recipe, llm)) == src
    assert llm.requests == []


@pytest.mark.parametrize("kind,expected", sorted(EXPECTED_PAGES.items()))
def test_mock_llm_falls_back_to_template_pages(kind: str, expected: int, tmp_path: Path):
    """演示模式（MockLLM）返回通用文本，不含页片段时必须兜底为模板内容，
    否则会渲染出结构散架的单页 PDF。"""
    pytest.importorskip("weasyprint")
    from app.llm import MockLLM

    out = tmp_path / f"mock_{kind}.pdf"
    asyncio.run(
        PDFTool().run(prompt="测试", output=out, kind=kind, llm=MockLLM())
    )
    pytest.importorskip("pymupdf")
    import pymupdf

    doc = pymupdf.open(out)
    assert doc.page_count == expected


@pytest.mark.parametrize("kind,expected", sorted(EXPECTED_PAGES.items()))
def test_content_param_regenerated_through_template(
    kind: str, expected: int, tmp_path: Path
):
    """传入 Markdown 只作素材，必须按模板骨架重组，不能被当 HTML 原样渲染。"""
    pytest.importorskip("weasyprint")
    from app.llm import MockLLM

    out = tmp_path / f"content_{kind}.pdf"
    asyncio.run(
        PDFTool().run(
            prompt="测试",
            output=out,
            kind=kind,
            content="# 用户传入的 Markdown\n\n这是正文。",
            llm=MockLLM(),
        )
    )
    pytest.importorskip("pymupdf")
    import pymupdf

    doc = pymupdf.open(out)
    assert doc.page_count == expected


@pytest.mark.parametrize("kind,expected", sorted(EXPECTED_PAGES.items()))
def test_end_to_end_page_count(kind: str, expected: int, tmp_path: Path):
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("weasyprint")

    out = tmp_path / f"{kind}.pdf"
    tool = PDFTool()
    result = asyncio.run(
        tool.run(
            prompt="测试",
            output=out,
            kind=kind,
            llm=StructuredLLM(get_recipe(kind)),
        )
    )
    assert result["theme"] == kind
    doc = pymupdf.open(out)
    assert doc.page_count == expected, f"{kind} 页数 {doc.page_count} ≠ {expected}"
    # 首页应有内容（不是空白页）
    assert len(doc[0].get_text().strip()) > 20
