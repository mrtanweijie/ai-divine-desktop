from app.docgen.pdf.renderer.markdown import _build_toc, _markdown_to_html
from app.tools.scripts.pdf_render import (
    _extract_leading_cover,
    _strip_own_toc,
    derive_title,
)


def test_markdown_to_html_basic():
    html = _markdown_to_html("# 标题\n\n正文")
    assert "<h1" in html
    assert "正文" in html


def test_build_toc_collects_h2_h3():
    toc = _build_toc("## 章节一\n\n### 小节\n\n## 章节二")
    assert "章节一" in toc
    assert "章节二" in toc


COVER_HTML = (
    '<div style="width:100%;height:100%;margin:0;'
    'page-break-after:always;position:relative;">'
    '<div style="font-size:40px;color:#0f2b5b;">摄影 / 摄像类<br/>'
    "商户画像数据分析报告</div></div>"
)


def test_extract_leading_cover():
    cover, rest = _extract_leading_cover(
        COVER_HTML + "\n\n# 目录\n\n1. 数据概览"
    )
    assert cover == COVER_HTML
    assert rest.startswith("# 目录")


def test_derive_title_from_html_cover():
    title = derive_title("", COVER_HTML + "\n\n# 目录")
    assert title == "摄影 / 摄像类 商户画像数据分析报告"


def test_derive_title_strips_html_in_explicit_title():
    title = derive_title("<div>摄影报告</div>", "# 正文")
    assert title == "摄影报告"


def test_strip_own_toc_keeps_next_heading():
    md = "# 目录\n\n1. 数据概览\n\n# 1. 数据概览\n\n正文"
    out = _strip_own_toc(md)
    assert "# 目录" not in out
    assert out.startswith("# 1. 数据概览")
