"""图表主题色重着色（docgen/chart/recolor.py）测试。

原缺陷：PDF 内嵌图表使用固定色板（奶油金等），不跟随文档主题色，
深蓝商务主题配奶油金柱子观感割裂。
"""

import re

from app.docgen.chart.recolor import (
    derive_series_palette,
    recolor_body_svg,
    recolor_chart_svg,
)
from app.docgen.chart.svg import COLORS, render_chart_svg


def _bar_svg() -> str:
    return render_chart_svg(
        {
            "xAxis": {"type": "category", "data": ["A", "B", "C"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "name": "系列", "data": [10, 20, 30]}],
        },
        "测试图表",
    )


# ---------------------------------------------------------------------------
# 色板派生
# ---------------------------------------------------------------------------

def test_derive_series_palette_blue():
    palette = derive_series_palette("#2563EB")
    assert palette is not None
    assert len(palette) == len(COLORS)
    # 键是图表色板（大写），值是派生 hex
    assert set(palette) == {color.upper() for color in COLORS}
    for derived in palette.values():
        assert re.fullmatch(r"#[0-9A-F]{6}", derived)
    # 派生色不与原色板重叠
    assert not (set(palette.values()) & {c.upper() for c in COLORS})


def test_derive_series_palette_named_color():
    """支持任意可解析色（颜色名/色值），黑色主题退化为低亮度色。"""
    assert derive_series_palette("红色") is not None
    gray_palette = derive_series_palette("#808080")
    assert gray_palette is not None


def test_derive_series_palette_invalid():
    assert derive_series_palette("不是一个颜色") is None
    assert derive_series_palette("") is None


# ---------------------------------------------------------------------------
# SVG 重着色
# ---------------------------------------------------------------------------

def test_recolor_replaces_palette_keeps_neutrals():
    svg = _bar_svg()
    palette = derive_series_palette("#2563EB")
    recolored = recolor_chart_svg(svg, palette)
    # 原色板全部消失
    for color in COLORS:
        assert color.upper() not in recolored.upper()
    # 中性色保留（标题墨色 #33475F）
    assert "#33475F" in recolored
    # 结构不变：rect 数量一致
    assert recolored.count("<rect") == svg.count("<rect")


def test_recolor_case_insensitive():
    svg = _bar_svg().replace(COLORS[0].upper(), COLORS[0].lower())
    palette = derive_series_palette("#2563EB")
    recolored = recolor_chart_svg(svg, palette)
    assert COLORS[0].lower() not in recolored
    assert COLORS[0].upper() not in recolored


def test_recolor_different_primaries_differ():
    svg = _bar_svg()
    blue = recolor_chart_svg(svg, derive_series_palette("#2563EB"))
    red = recolor_chart_svg(svg, derive_series_palette("#E74C3C"))
    assert blue != red


# ---------------------------------------------------------------------------
# HTML body 处理（内联 SVG + <img src="*.svg">）
# ---------------------------------------------------------------------------

def test_recolor_body_inline_svg(tmp_path):
    svg = _bar_svg()
    body = f'<div class="illustration">{svg}</div>'
    recolored = recolor_body_svg(body, "#2563EB")
    for color in COLORS:
        assert color.upper() not in recolored.upper()


def test_recolor_body_img_svg(tmp_path):
    chart_file = tmp_path / "charts" / "demo.svg"
    chart_file.parent.mkdir()
    chart_file.write_text(_bar_svg(), encoding="utf-8")
    body = '<p>图</p><img alt="图表" src="charts/demo.svg">'
    recolored = recolor_body_svg(body, "#2563EB", base_dir=tmp_path)
    # 本地 svg 被重着色并内嵌为 data URI
    assert 'src="charts/demo.svg"' not in recolored
    assert "data:image/svg+xml;base64," in recolored
    import base64

    payload = re.search(
        r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", recolored
    ).group(1)
    decoded = base64.b64decode(payload).decode("utf-8")
    for color in COLORS:
        assert color.upper() not in decoded.upper()


def test_recolor_body_skips_missing_files_and_remote(tmp_path):
    body = (
        '<img src="charts/missing.svg">'
        '<img src="https://example.com/a.svg">'
    )
    recolored = recolor_body_svg(body, "#2563EB", base_dir=tmp_path)
    assert recolored == body


def test_recolor_body_no_primary_noop():
    svg = _bar_svg()
    body = f"<div>{svg}</div>"
    assert recolor_body_svg(body, None) == body
    assert recolor_body_svg(body, "不是颜色") == body
