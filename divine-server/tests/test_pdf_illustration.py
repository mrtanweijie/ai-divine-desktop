"""通用配图（illustration.py）与配图提示注入测试。"""

from app.docgen.pdf import illustration
from app.docgen.pdf.base import PDFIntent, PDFRecipe
from app.docgen.pdf.content import _system_prompt
from app.docgen.pdf.illustration import inline_markdown_images, placeholder_html
from app.docgen.pdf.recipes import ReportRecipe, TravelRecipe


def test_placeholder_html_escapes_caption():
    html = placeholder_html("城市 <夜景>")
    assert "<夜景>" not in html
    assert "城市" in html
    assert "img-fallback" in html


def test_local_image_paths_untouched():
    markdown = "![图](assets/local.png) 与 ![图二](/abs/path.jpg)"
    assert inline_markdown_images(markdown) == markdown


def test_keyword_image_inlined(monkeypatch):
    monkeypatch.setattr(
        illustration, "_image_data_uri", lambda url: "data:image/png;base64,AAA"
    )
    captured = {}
    monkeypatch.setattr(
        illustration,
        "_keyword_to_image_url",
        lambda kw: captured.setdefault("kw", kw) or "https://picsum/x",
    )
    out = inline_markdown_images("![西湖日落](keyword:西湖日落)")
    assert "data:image/png;base64,AAA" in out
    assert captured["kw"] == "西湖日落"
    assert "keyword:" not in out


def test_keyword_image_failure_degrades_to_placeholder(monkeypatch):
    monkeypatch.setattr(illustration, "_image_data_uri", lambda url: None)
    out = inline_markdown_images("![配图说明](keyword:城市)")
    assert "img-fallback" in out
    assert "配图说明" in out


def test_remote_url_failure_degrades_to_placeholder(monkeypatch):
    monkeypatch.setattr(illustration, "_image_data_uri", lambda url: None)
    out = inline_markdown_images("![真实图](https://example.com/a.png)")
    assert "img-fallback" in out
    assert "https://example.com/a.png" not in out


def test_remote_url_success_inlined(monkeypatch):
    monkeypatch.setattr(
        illustration, "_image_data_uri", lambda url: "data:image/jpeg;base64,BBB"
    )
    out = inline_markdown_images("![真实图](https://cdn.example.com/a.jpg)")
    assert "data:image/jpeg;base64,BBB" in out


def test_inline_limit_reached_keeps_original_remote_url(monkeypatch):
    monkeypatch.setattr(
        illustration, "_image_data_uri", lambda url: "data:image/png;base64,C"
    )
    markdown = "".join(
        f"![图{i}](https://example.com/{i}.png)\n\n" for i in range(15)
    )
    out = inline_markdown_images(markdown)
    assert out.count("data:image/png;base64,C") == illustration._MAX_INLINE_IMAGES
    assert "https://example.com/14.png" in out  # 超限的保留原样


def test_no_image_syntax_untouched():
    markdown = "# 标题\n\n正文没有图片。"
    assert inline_markdown_images(markdown) == markdown


def test_system_prompt_appends_illustration_hint():
    intent = PDFIntent(
        title="报告",
        topic="主题",
        style="universal",
        color_scheme="blue",
        sections=[],
        meta={"images_requested": True},
    )
    prompt = _system_prompt(intent, ReportRecipe())
    assert "keyword:" in prompt
    assert "【配图" in prompt


def test_system_prompt_no_hint_without_images_flag():
    intent = PDFIntent(
        title="报告",
        topic="主题",
        style="universal",
        color_scheme="blue",
        sections=[],
        meta={},
    )
    prompt = _system_prompt(intent, ReportRecipe())
    assert "keyword:" not in prompt


def test_system_prompt_travel_html_never_gets_hint():
    intent = PDFIntent(
        title="攻略",
        topic="主题",
        style="travel",
        color_scheme="teal",
        sections=[],
        meta={"images_requested": True},
    )
    assert _system_prompt(intent, TravelRecipe()) == (
        TravelRecipe.content_system_prompt(TravelRecipe(), intent)
    )
