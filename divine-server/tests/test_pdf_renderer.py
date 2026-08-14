from app.pdf_renderer.markdown import _build_toc, _markdown_to_html


def test_markdown_to_html_basic():
    html = _markdown_to_html("# 标题\n\n正文")
    assert "<h1" in html
    assert "正文" in html


def test_build_toc_collects_h2_h3():
    toc = _build_toc("## 章节一\n\n### 小节\n\n## 章节二")
    assert "章节一" in toc
    assert "章节二" in toc
