"""测试布局模块：markdown 约定转换、主题 CSS 挂载、Agent prompt 接入。"""

from app.docgen.pdf.theme_manager import load_theme_css
from app.docgen.pdf.renderer.markdown import (
    _build_toc,
    _convert_modules,
    _prepare_markdown,
)
from app.docgen.pdf.base import MODULE_GUIDE
from app.docgen.pdf.recipes import ReportRecipe


# ---------------------------------------------------------------------------
# 转换器：引用块约定
# ---------------------------------------------------------------------------

def test_quote_block_becomes_pull_quote():
    md = """> [!quote] 关键洞察
> 双塔模型让召回效率提升 2.3 倍。
> — 算法团队
"""
    out = _convert_modules(md)
    assert 'class="module pull-quote"' in out
    assert 'data-emphasis="medium"' in out
    assert "双塔模型让召回效率提升 2.3 倍。" in out
    assert 'class="attribution"' in out
    assert "算法团队" in out


def test_callout_variants():
    for kind in ("note", "info", "warning", "success", "error"):
        out = _convert_modules(f"> [!{kind}] 标题\n> 内容\n")
        assert f'class="callout-box {kind}"' in out, kind
        assert "内容" in out, kind


def test_callout_icon_uses_text_char():
    # WeasyPrint 66 不渲染 CSS stroke 的内联 SVG，图标用文本字符保证可见
    out = _convert_modules("> [!warning] 注意\n> 内容\n")
    assert "<svg" not in out
    assert "⚠" in out
    assert 'class="ci"' in out


def test_conclusion_and_bio():
    out = _convert_modules("> [!conclusion] 下一步\n> Q3 完成多活部署。\n")
    assert 'class="module conclusion-box"' in out
    assert "Q3 完成多活部署。" in out

    out = _convert_modules("> [!bio] 张三 | 首席架构师\n> 10 年后端经验。\n")
    assert 'class="module bio-card"' in out
    assert "张三" in out and "首席架构师" in out
    assert "张三" in out  # 头像缩写取名前两字


def test_plain_blockquote_untouched():
    md = "> 普通引用\n> 第二行\n"
    out = _convert_modules(md)
    assert "pull-quote" not in out
    assert "> 普通引用" in out  # 保持原样交给 markdown 库


# ---------------------------------------------------------------------------
# 转换器：表格标记约定
# ---------------------------------------------------------------------------

def test_hero_stat_table():
    md = """| 指标 | 数值 | 变化 |
| --- | --- | --- |
| DAU | 2.4M | +34% |
| 留存率 | 42% | -8% |
{: .hero-stat}
"""
    out = _convert_modules(md)
    assert 'class="module hero-stat"' in out
    assert "DAU" in out
    assert "2.4" in out and 'class="stat-unit">M<' in out  # 数值与单位拆分
    assert 'class="stat-trend up"' in out
    assert 'class="stat-trend down"' in out


def test_compare_table():
    md = """| 改版前 | 改版后 |
| --- | --- |
| 协同过滤 | 双塔模型 |
{: .compare}
"""
    out = _convert_modules(md)
    assert 'class="module two-col-compare"' in out
    assert "协同过滤" in out and "双塔模型" in out
    assert "VS" in out


def test_timeline_table_with_highlight():
    md = """| 时间 | 事件 | 说明 | 高亮 |
| --- | --- | --- | --- |
| 2026.04 | 离线验证 | HitRate +35% | yes |
| 2026.05 | A/B 测试 | 5% 流量 | |
{: .timeline}
"""
    out = _convert_modules(md)
    assert 'class="module timeline"' in out
    assert 'timeline-node highlight' in out
    assert 'timeline-node"' in out  # 非高亮节点
    assert "离线验证" in out


def test_features_metrics_tags():
    out = _convert_modules("| 🚀 | 秒级部署 | 30s |\n| 🔒 | 零信任 | mTLS |\n{: .features}\n")
    assert 'class="module feature-grid"' in out
    assert "秒级部署" in out

    out = _convert_modules("| DAU | 2.4M/3M | 80% |\n{: .metrics}\n")
    assert 'class="module metric-row"' in out
    assert 'width:80%' in out

    out = _convert_modules("| Go | yes |\n| Redis | |\n{: .tags}\n")
    assert 'class="module tag-cloud"' in out
    assert 'class="tag hl"' in out
    assert 'class="tag"' in out


def test_multiple_marked_tables_do_not_merge():
    md = """| A | B | C |
| --- | --- | --- |
| 1 | 2 | 3 |
{: .hero-stat}

| X | Y |
| --- | --- |
| a | b |
{: .compare}
"""
    out = _convert_modules(md)
    assert 'class="module hero-stat"' in out
    assert 'class="module two-col-compare"' in out


def test_unknown_table_mark_untouched():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n{: .unknown}\n"
    out = _convert_modules(md)
    assert "hero-stat" not in out
    assert "{: .unknown}" in out  # 留给 markdown 库（attr_list）处理


def test_content_is_escaped():
    md = "> [!note] 说明\n> <script>alert(1)</script>\n"
    out = _convert_modules(md)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


# ---------------------------------------------------------------------------
# 主题 CSS 挂载
# ---------------------------------------------------------------------------

def test_theme_css_contains_module_styles():
    css = load_theme_css("universal")
    for token in (
        ".hero-stat",
        ".pull-quote",
        ".two-col-compare",
        ".timeline-track",
        ".feature-grid",
        ".callout-box",
        ".metric-row",
        ".bio-card",
        ".tag-cloud",
        ".conclusion-box",
    ):
        assert token in css, token


def test_travel_css_skips_module_styles():
    css = load_theme_css("travel")
    assert ".hero-stat" not in css  # travel 走独立模板，不注入模块样式


# ---------------------------------------------------------------------------
# Agent prompt 接入
# ---------------------------------------------------------------------------

def test_report_prompt_embeds_module_guide():
    recipe = ReportRecipe()
    prompt = recipe.content_system_prompt(
        __import__("app.docgen.pdf.base", fromlist=["PDFIntent"]).PDFIntent(
            title="测试", topic="测试主题", style="universal", color_scheme="blue"
        )
    )
    assert MODULE_GUIDE in prompt
    assert "{: .hero-stat}" in prompt
    assert "[!quote]" in prompt


def test_prepare_markdown_pipeline():
    md = """> [!warning] 注意
> 需要审批。

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32"/></svg>
```
"""
    out = _prepare_markdown(md)
    assert 'class="callout-box warning"' in out
    assert 'class="illustration"' in out


# ---------------------------------------------------------------------------
# TOC 目录模块（design_preview 风格）
# ---------------------------------------------------------------------------

def test_build_toc_uses_toc_item_structure():
    toc = _build_toc("## 核心指标\n\n### 关键洞察\n\n## 下一步计划")
    assert '<div class="toc">' in toc
    assert '<h2>目录</h2>' in toc
    assert 'class="toc-item toc-level-2"' in toc
    assert 'class="toc-item toc-level-3"' in toc
    assert '<span class="num">01</span>' in toc
    assert '<span class="num">02</span>' in toc
    assert 'class="title" href="#' in toc
    assert "<ul>" not in toc  # 不再是列表结构


def test_theme_css_contains_toc_styles():
    css = load_theme_css("universal")
    assert ".toc-item" in css
    assert "target-counter" in css  # 自动页码
    assert ".toc-item .num" in css


def test_pull_quote_resets_theme_blockquote():
    # 主题 blockquote 自带浅底+左边框；模块必须重置，避免两层包裹
    css = load_theme_css("universal")
    quote_idx = css.index(".pull-quote blockquote")
    theme_idx = css.index("blockquote {")
    assert quote_idx > theme_idx  # 重置规则在主题规则之后（可覆盖）
    assert "font-style: normal" in css[quote_idx:]
    assert "border: none" in css[quote_idx:]
