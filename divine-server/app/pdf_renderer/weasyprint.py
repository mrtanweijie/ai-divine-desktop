"""WeasyPrint renderer with lazy availability detection."""

from __future__ import annotations

import contextlib
import html as html_lib
import importlib.util
import io
import re
from pathlib import Path
from typing import Any

from .markdown import _add_heading_ids, _build_toc, _prepare_markdown
from .styles import COLOR_MAP


def _color_scheme_overrides(color_scheme: str) -> dict[str, str]:
    """把预设配色（blue/green/warm/monochrome/purple）映射为 CSS 变量覆盖。

    WeasyPrint 渲染路径此前忽略 color_scheme，主题色恒为默认蓝；
    这里用 COLOR_MAP 的主色覆盖 --primary/--primary-light/--accent，
    使 hero-stat、标题、表格、封面等模块配色随 color_scheme 变化。
    """
    colors = COLOR_MAP.get(color_scheme or "")
    if not colors:
        return {}
    accent = colors["accent"]
    return {
        "--primary": accent,
        "--primary-light": colors["light"],
        "--primary-dark": colors.get("dark", accent),
        "--accent": accent,
    }

_WEASYPRINT_OK: bool | None = None

def _weasyprint_available() -> bool:
    global _WEASYPRINT_OK
    if _WEASYPRINT_OK is not None:
        return _WEASYPRINT_OK
    if importlib.util.find_spec("weasyprint") is None:
        _WEASYPRINT_OK = False
        return False
    # cffi may resolve system libraries through the process environment even
    # when common paths cannot be found, so always attempt the import once.
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            import weasyprint  # noqa: F401

            _WEASYPRINT_OK = True
        except Exception:
            _WEASYPRINT_OK = False
    return _WEASYPRINT_OK

def _render_with_weasyprint(
    markdown: str,
    output: Path,
    title: str,
    style: str,
    color_scheme: str,
    paper_size: str,
    cover: bool,
    toc: bool,
    base_dir: Path | None = None,
    theme: str = "universal",
    cover_data: dict[str, Any] | None = None,
) -> None:
    from weasyprint import HTML

    import markdown as markdown_lib

    from ..pdf_theme_manager import build_cover_html, load_theme_css

    css = load_theme_css(
        theme,
        overrides=_color_scheme_overrides(color_scheme),
        paper_size=paper_size,
    )
    css += (
        "\nimg { max-width: 100%; height: auto; }\n"
        "figure, .illustration { text-align: center; }\n"
        # .header 必须为 running，否则普通 div 占流会把封面挤到第 2 页产生空白页
        ".header { position: running(header); }\n"
    )
    prepared = _prepare_markdown(markdown)
    body = markdown_lib.markdown(
        prepared,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    # 给 h2/h3 注入 id，供目录 target-counter 页码与锚点跳转使用
    body = _add_heading_ids(body)
    cover_html = ""
    if cover:
        custom_cover = ""
        if cover_data and cover_data.get("cover_html"):
            custom_cover = str(cover_data["cover_html"]).strip()
        if custom_cover:
            cover_html = (
                '<div style="page: cover-page; width:100%; height:100%; margin:0;">'
                f"{custom_cover}</div>"
            )
        else:
            # 有封面时正文不再重复渲染一级标题（封面已展示文档标题）
            body = re.sub(
                r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.DOTALL
            )
            # 副标题优先取文档摘要（summary），否则兜底文案
            subtitle = "AI Divine 生成文档"
            if cover_data and cover_data.get("summary"):
                subtitle = str(cover_data["summary"])
            cover_html = build_cover_html(
                theme,
                html_lib.escape(title),
                subtitle,
                cover_data,
            )
        # 封面 absolute 定位不占流：占位元素（page: cover-page）决定第 1 页为
        # 零边距封面页，page-break-after 把正文推到第 2 页（默认页）。
        # 自定义封面已自带 page-break-after 时不再重复分页，避免空白页。
        if not custom_cover or "page-break-after" not in custom_cover.lower():
            cover_html += (
                '<div style="page: cover-page; height: 0; '
                'page-break-after: always;"></div>'
            )
    toc_html = _build_toc(markdown) if toc else ""
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{cover_html}{toc_html}{body}</body></html>"
    )
    kwargs: dict[str, Any] = {"string": document}
    if base_dir is not None:
        kwargs["base_url"] = str(base_dir)
    HTML(**kwargs).write_pdf(str(output), presentational_hints=True)
