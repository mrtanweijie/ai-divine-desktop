"""简历换色（colorize.py）回归：色词/hex 解析、HSL 派生、模板变量注入与字面替换。"""

import re

import pytest

from app.docgen.resume.models import ResumeData
from app.docgen.resume.sample_data import SAMPLE_RESUME
from app.docgen.resume.templates import build_html, render_template_resume
from app.docgen.resume.templates.colorize import (
    RESUME_SLOTS,
    apply_resume_color,
    derive_resume_palette,
    resolve_color,
)

_CSS = (
    ":root{--navy:#16233a;--gold:#a8874f;}\n"
    ".toolbar{background:#16233a}\n.foo{color:var(--navy)}"
)


@pytest.mark.parametrize(
    ("text", "hex"),
    [
        ("石墨墨黑", "#2B2B2B"),
        ("石墨墨黑配色", "#2B2B2B"),
        ("石墨墨黑 #2B2B2B", "#2B2B2B"),
        ("#2b2b2b", "#2B2B2B"),
        ("rgb(43,43,43)", "#2B2B2B"),
        ("藏青", "#1F3A5F"),
        ("藏青色", "#1F3A5F"),
        ("红色", "#E74C3C"),
        ("blue", "#2F5B9E"),
    ],
)
def test_resolve_color(text: str, hex: str) -> None:
    rgb = resolve_color(text)
    assert rgb is not None
    assert "#%02X%02X%02X" % rgb == hex


@pytest.mark.parametrize("text", ["", "iceblue", "青花瓷色", "None"])
def test_resolve_color_unresolvable(text: str) -> None:
    assert resolve_color(text) is None


def test_derive_palette_keeps_dark_primary_and_darkens_light() -> None:
    graphite = derive_resume_palette((43, 43, 43))  # 石墨墨黑：中性深色原样保留
    assert graphite["main"] == "#2B2B2B"
    assert graphite["accent"].startswith("#") and graphite["accent"] != graphite["main"]
    assert graphite["soft"].startswith("#")
    yellow = derive_resume_palette((212, 160, 23))  # 亮黄主色压暗，保证白字可读
    r, g, b = (int(yellow["main"][i:i + 2], 16) for i in (1, 3, 5))
    import colorsys

    lum = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[1]
    assert lum <= 0.5


def test_apply_resume_color_injects_overrides_and_replaces_literals() -> None:
    css = apply_resume_color(_CSS, "tpl_executive", color_scheme="石墨墨黑")
    assert ":root{--navy:#2B2B2B;--gold:" in css  # 变量覆盖
    assert "#16233a" not in css.lower()  # 硬编码旧主色（toolbar 等）同步替换
    assert ".foo{color:var(--navy)}" in css


def test_apply_resume_color_monochrome_template_unchanged() -> None:
    css = apply_resume_color(_CSS, "tpl_minimal", color_scheme="#E74C3C")
    assert css == _CSS  # 无槽位模板优雅降级，保持默认


def test_apply_resume_color_var_overrides_win_over_scheme() -> None:
    css = apply_resume_color(
        _CSS, "tpl_executive", color_scheme="石墨墨黑",
        color_overrides={"--navy": "#5B2CD9"},
    )
    assert "--navy:#5B2CD9" in css  # 显式变量覆盖优先于主色派生
    assert "--gold:#5C5C5C" in css  # 派生强调色仍按主色生成


def _html(tid: str, **kwargs) -> str:
    resume = ResumeData.from_dict(SAMPLE_RESUME)
    return build_html(resume, tid, "multi", editable=False, **kwargs)


def test_build_html_color_scheme_in_style() -> None:
    html = _html("tpl_executive", color_scheme="石墨墨黑")
    assert ":root{--navy:#2B2B2B;" in html
    html_clean = _html("tpl_global", color_scheme="#2B2B2B")
    assert ":root{--eu:#2B2B2B;" in html_clean


@pytest.mark.parametrize("tid", list(RESUME_SLOTS))
def test_all_slotted_templates_render_with_scheme(tid: str) -> None:
    html = _html(tid, color_scheme="#2B2B2B")
    assert "<style>:root" in html


def test_render_template_resume_both_html_files_carry_color(tmp_path) -> None:
    resume = ResumeData.from_dict(SAMPLE_RESUME)
    files = render_template_resume(
        resume, str(tmp_path / "换色.html"), "tpl_executive", "multi", "html",
        color_scheme="石墨墨黑",
    )
    assert len(files) == 2
    for path in files:
        assert "--navy:#2B2B2B" in open(path, encoding="utf-8").read()
