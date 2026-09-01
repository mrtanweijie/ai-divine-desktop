"""PPT 主题注册表、装饰语言（style）与低层绘制助手。

主题 token：颜色 / 字体 / 图表调色板；style：装饰语言（顶条、卡片、
封面构图等的画法），所有版式统一从主题取 token、从 style 取画法，
保证封面、正文、图表、表格在同一主题下视觉一致。
"""

from __future__ import annotations

from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# 现代设计预设（与 docs/PPT模板设计预览.html 一一对应）+ 经典色彩主题。
# style 字段选择装饰语言；chart_palette 供原生图表与 SVG 复杂图表共用。
PPT_THEMES: dict[str, dict[str, Any]] = {
    # ---- 现代设计预设 ----
    "aurora": {
        "style": "aurora",
        "cover_bg": "141133", "content_bg": "FFFFFF", "accent": "7C3AED",
        "accent2": "22D3EE", "accent_light": "F6F4FF", "text": "232052",
        "muted": "6E6A96", "cover_text": "FFFFFF", "meta": "CBC5F4",
        "font": "PingFang SC",
        "chart_palette": ["7C3AED", "22D3EE", "A78BFA", "F59E0B", "10B981"],
    },
    "glass": {
        "style": "glass",
        "cover_bg": "EAF0FB", "content_bg": "FFFFFF", "accent": "4F46E5",
        "accent2": "0EA5E9", "accent_light": "EDF2FC", "text": "1E2A55",
        "muted": "5D6A94", "cover_text": "1E2A55", "meta": "6B76A0",
        "font": "PingFang SC",
        "chart_palette": ["4F46E5", "0EA5E9", "8B5CF6", "14B8A6", "F59E0B"],
    },
    "brutalist": {
        "style": "brutalist",
        "cover_bg": "FAF6EE", "content_bg": "FAF6EE", "accent": "FF5C00",
        "accent2": "2563EB", "accent_light": "FFFFFF", "text": "111111",
        "muted": "4A4A42", "cover_text": "111111", "meta": "3E3E36",
        "font": "PingFang SC",
        "chart_palette": ["FF5C00", "2563EB", "111111", "D97706", "059669"],
    },
    "swiss": {
        "style": "swiss",
        "cover_bg": "FAFAF7", "content_bg": "FAFAF7", "accent": "DA291C",
        "accent2": "111111", "accent_light": "FFFFFF", "text": "111111",
        "muted": "777772", "cover_text": "111111", "meta": "8A8A82",
        "font": "PingFang SC",
        "chart_palette": ["DA291C", "111111", "2563EB", "0891B2", "777772"],
    },
    "mesh": {
        "style": "mesh",
        "cover_bg": "0A0A1C", "content_bg": "FFFFFF", "accent": "6366F1",
        "accent2": "06B6D4", "accent_light": "F4F5FF", "text": "1E1B4B",
        "muted": "64748B", "cover_text": "F9FAFB", "meta": "94A3B8",
        "font": "PingFang SC",
        "chart_palette": ["6366F1", "06B6D4", "A855F7", "EC4899", "10B981"],
    },
    "editorial": {
        "style": "editorial",
        "cover_bg": "F7F3EA", "content_bg": "FDFBF6", "accent": "C2410C",
        "accent2": "1C1917", "accent_light": "F7F3EA", "text": "1C1917",
        "muted": "78716C", "cover_text": "1C1917", "meta": "A8A29E",
        "font": "PingFang SC", "heading_font": "Noto Serif SC",
        "chart_palette": ["C2410C", "1C1917", "B45309", "065F46", "78716C"],
    },
    "darktech": {
        "style": "darktech",
        "cover_bg": "0B0F1A", "content_bg": "0B0F1A", "accent": "22D3EE",
        "accent2": "A78BFA", "accent_light": "111827", "text": "E5E7EB",
        "muted": "8B93A7", "cover_text": "F9FAFB", "meta": "9CA3AF",
        "font": "PingFang SC",
        "chart_palette": ["22D3EE", "A78BFA", "34D399", "F472B6", "60A5FA"],
    },
    # ---- 经典色彩主题（style 指向最接近的装饰语言）----
    "universal": {
        "style": "clean",
        "cover_bg": "10131A", "content_bg": "FFFFFF", "accent": "2563EB",
        "accent2": "0EA5E9", "accent_light": "EFF6FF", "text": "1A1D24",
        "muted": "6B7280", "cover_text": "FFFFFF", "meta": "9AA3B2",
        "font": "PingFang SC",
        "chart_palette": ["2563EB", "0EA5E9", "7C3AED", "10B981", "F59E0B"],
    },
    "modern": {
        "style": "aurora",
        "cover_bg": "141133", "content_bg": "FFFFFF", "accent": "2563EB",
        "accent2": "22D3EE", "accent_light": "EFF6FF", "text": "1A1D24",
        "muted": "6B7280", "cover_text": "FFFFFF", "meta": "9AA3B2",
        "font": "PingFang SC",
        "chart_palette": ["2563EB", "0EA5E9", "7C3AED", "10B981", "F59E0B"],
    },
    "notion": {
        "style": "clean",
        "cover_bg": "FFFFFF", "content_bg": "FFFFFF", "accent": "37352F",
        "accent2": "9B9B97", "accent_light": "F7F6F3", "text": "37352F",
        "muted": "9B9B97", "cover_text": "37352F", "meta": "B9B9B5",
        "font": "PingFang SC",
        "chart_palette": ["37352F", "9B9B97", "D9730D", "2F6FEB", "5B8A72"],
    },
    "linear": {
        "style": "clean",
        "cover_bg": "202129", "content_bg": "FFFFFF", "accent": "5E6AD2",
        "accent2": "8B5CF6", "accent_light": "F0F1FF", "text": "202129",
        "muted": "5C5F6E", "cover_text": "FFFFFF", "meta": "8F92A3",
        "font": "PingFang SC",
        "chart_palette": ["5E6AD2", "8B5CF6", "0EA5E9", "22C55E", "F59E0B"],
    },
    "apple": {
        "style": "clean",
        "cover_bg": "F5F5F7", "content_bg": "FFFFFF", "accent": "0071E3",
        "accent2": "30D158", "accent_light": "E8F2FF", "text": "1D1D1F",
        "muted": "6E6E73", "cover_text": "1D1D1F", "meta": "AEAEB2",
        "font": "PingFang SC",
        "chart_palette": ["0071E3", "30D158", "FF9F0A", "BF5AF2", "64D2FF"],
    },
    "academic": {
        "style": "editorial",
        "cover_bg": "F7FAFC", "content_bg": "FFFFFF", "accent": "742A2A",
        "accent2": "2C5282", "accent_light": "FEF5F5", "text": "1A202C",
        "muted": "718096", "cover_text": "1A202C", "meta": "A0AEC0",
        "font": "Noto Serif SC",
        "chart_palette": ["742A2A", "2C5282", "276749", "975A16", "6B46C1"],
    },
    "travel": {
        "style": "clean",
        "cover_bg": "FFF7ED", "content_bg": "FFFDF7", "accent": "EA580C",
        "accent2": "D97706", "accent_light": "FFF3E6", "text": "1C1917",
        "muted": "A8A29E", "cover_text": "9A3412", "meta": "FB923C",
        "font": "PingFang SC",
        "chart_palette": ["EA580C", "D97706", "059669", "0EA5E9", "DC2626"],
    },
    "roadmap": {
        "style": "aurora",
        "cover_bg": "1E1B4B", "content_bg": "FFFFFF", "accent": "7C3AED",
        "accent2": "A855F7", "accent_light": "F3E8FF", "text": "1E1B4B",
        "muted": "A78BFA", "cover_text": "FFFFFF", "meta": "C4B5FD",
        "font": "PingFang SC",
        "chart_palette": ["7C3AED", "4F46E5", "A855F7", "0EA5E9", "EC4899"],
    },
    "minimal": {
        "style": "clean",
        "cover_bg": "FFFFFF", "content_bg": "FFFFFF", "accent": "222222",
        "accent2": "666666", "accent_light": "F5F5F5", "text": "222222",
        "muted": "999999", "cover_text": "111111", "meta": "BBBBBB",
        "font": "PingFang SC",
        "chart_palette": ["222222", "666666", "3B82F6", "10B981", "999999"],
    },
}

DEFAULT_THEME = "universal"

# 装饰语言注册表：每种 style 一组画法参数，版式渲染按这里分支。
STYLES: dict[str, dict[str, Any]] = {
    "clean": {
        "topbar": "solid", "topbar_h": 0.09,
        "card_radius": 0.07, "card_border_auto": True, "card_border": None,
        "card_shadow": False, "card_toprule": None, "card_dot_square": False,
        "cover": "clean", "section_bg": "content", "cover_centered": False,
        "bg_decor": None, "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "accent_light_mix", "timeline_dot_square": False,
        "toc_rule": "muted_mix", "quote_serif": False, "kicker_mono": False,
    },
    "aurora": {
        "topbar": "gradient", "topbar_h": 0.09,
        "card_radius": 0.07, "card_border_auto": True, "card_border": None,
        "card_shadow": False, "card_toprule": None, "card_dot_square": False,
        "cover": "gradient_blobs", "section_bg": "dark", "cover_centered": False,
        "bg_decor": None, "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "accent_light_mix", "timeline_dot_square": False,
        "toc_rule": "accent_light", "quote_serif": False, "kicker_mono": False,
    },
    "glass": {
        "topbar": "gradient", "topbar_h": 0.09,
        "card_radius": 0.07, "card_border_auto": True, "card_border": None,
        "card_shadow": False, "card_toprule": None, "card_dot_square": False,
        "cover": "glass_panel", "section_bg": "content", "cover_centered": False,
        "bg_decor": "blob", "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "accent_light_mix", "timeline_dot_square": False,
        "toc_rule": "accent_light", "quote_serif": False, "kicker_mono": False,
    },
    "brutalist": {
        "topbar": "solid_dark", "topbar_h": 0.11,
        "card_radius": 0.0, "card_border_auto": False, "card_border": "text",
        "card_border_w": 2.5, "card_shadow": True, "card_toprule": None,
        "card_dot_square": True,
        "cover": "blocks", "section_bg": "content", "cover_centered": False,
        "bg_decor": None, "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "text", "timeline_dot_square": True,
        "toc_rule": "text", "quote_serif": False, "kicker_mono": False,
    },
    "swiss": {
        "topbar": "none", "topbar_h": 0.0,
        "card_radius": 0.0, "card_border_auto": False, "card_border": None,
        "card_shadow": False, "card_toprule": "text", "card_dot_square": True,
        "cover": "swiss_index", "section_bg": "content", "cover_centered": False,
        "bg_decor": None, "heading_rule": "text", "heading_rule_h": 0.035,
        "corner_mark": True, "serif_heading": False, "index_serif": False,
        "timeline_track": "text", "timeline_dot_square": True,
        "toc_rule": "text", "quote_serif": False, "kicker_mono": False,
    },
    "mesh": {
        "topbar": "gradient", "topbar_h": 0.09,
        "card_radius": 0.07, "card_border_auto": True, "card_border": None,
        "card_shadow": False, "card_toprule": None, "card_dot_square": False,
        "cover": "gradient_blobs", "section_bg": "dark", "cover_centered": True,
        "bg_decor": None, "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "accent_light_mix", "timeline_dot_square": False,
        "toc_rule": "accent_light", "quote_serif": False, "kicker_mono": True,
    },
    "editorial": {
        "topbar": "none", "topbar_h": 0.0,
        "card_radius": 0.0, "card_border_auto": False, "card_border": None,
        "card_shadow": False, "card_toprule": "hairline", "card_dot_square": True,
        "cover": "editorial", "section_bg": "content", "cover_centered": True,
        "bg_decor": None, "heading_rule": "hairline", "heading_rule_h": 0.014,
        "corner_mark": False, "serif_heading": True, "index_serif": True,
        "timeline_track": "hairline", "timeline_dot_square": True,
        "toc_rule": "hairline", "quote_serif": True, "kicker_mono": False,
    },
    "darktech": {
        "topbar": "gradient", "topbar_h": 0.09,
        "card_radius": 0.05, "card_border_auto": False, "card_border": None,
        "card_shadow": False, "card_toprule": None, "card_dot_square": False,
        "card_neon_left": True,
        "cover": "darktech", "section_bg": "dark", "cover_centered": False,
        "bg_decor": "grid", "heading_rule": None, "heading_rule_h": 0.0,
        "corner_mark": False, "serif_heading": False, "index_serif": False,
        "timeline_track": "muted_mix", "timeline_dot_square": False,
        "toc_rule": "muted_mix", "quote_serif": False, "kicker_mono": True,
    },
}


def get_ppt_theme(theme_id: str | None) -> dict[str, Any]:
    return PPT_THEMES.get((theme_id or "").strip(), PPT_THEMES[DEFAULT_THEME])


def get_style(theme: dict[str, Any]) -> dict[str, Any]:
    """主题 token + 装饰语言画法参数合并视图。"""
    style_key = theme.get("style", "clean")
    merged = dict(STYLES["clean"])
    merged.update(STYLES.get(style_key, STYLES["clean"]))
    return merged


def blend(c1: str, c2: str, t: float) -> str:
    """把两个 hex 颜色按 t（0=c1，1=c2）混合，返回 hex。"""
    a = [int(c1[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(a[i] + (b[i] - a[i]) * t):02X}" for i in range(3))


def is_light(hex_color: str) -> bool:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.65


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def solid(shape: Any, color: str, line: str | None = None) -> Any:
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    if line:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Pt(0.75)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def set_alpha(shape: Any, opacity_pct: float) -> Any:
    """给纯色填充叠加透明度（opacity_pct：0-100，100 为不透明）。"""
    sp_pr = shape.fill._xPr
    solid_fill = sp_pr.find(qn("a:solidFill"))
    if solid_fill is None:
        return shape
    srgb = solid_fill.find(qn("a:srgbClr"))
    if srgb is None:
        return shape
    for old in srgb.findall(qn("a:alpha")):
        srgb.remove(old)
    alpha = srgb.makeelement(qn("a:alpha"), {"val": str(int(opacity_pct * 1000))})
    srgb.append(alpha)
    return shape


def gradient(shape: Any, c1: str, c2: str, angle: float = 115.0) -> Any:
    """双色线性渐变填充。"""
    fill = shape.fill
    fill.gradient()
    stops = fill.gradient_stops
    stops[0].color.rgb = rgb(c1)
    stops[0].position = 0.0
    stops[1].color.rgb = rgb(c2)
    stops[1].position = 1.0
    try:
        fill.gradient_angle = angle
    except Exception:  # noqa: BLE001 — 部分渐变类型不支持角度，保持默认
        pass
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def set_run(run: Any, size: float, color: str, bold: bool = False,
            font: str | None = None, italic: bool = False,
            letter_spacing_pt: float | None = None) -> Any:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = rgb(color)
    run.font.name = font or "PingFang SC"
    r_pr = run._r.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = r_pr.makeelement(qn("a:ea"), {})
        r_pr.append(ea)
    ea.set("typeface", font or "PingFang SC")
    if letter_spacing_pt:
        r_pr.set("spc", str(int(letter_spacing_pt * 100)))
    return run


def add_textbox(slide: Any, x: float, y: float, w: float, h: float) -> Any:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    for margin in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, margin, 0)
    return box


def add_rect(slide: Any, x: float, y: float, w: float, h: float,
             color: str, rounded: bool = False, radius: float = 0.08) -> Any:
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    if rounded:
        try:
            shape.adjustments[0] = radius
        except Exception:  # noqa: BLE001 — 圆角系数不可调时保持默认
            pass
    return solid(shape, color)


def add_oval(slide: Any, x: float, y: float, w: float, h: float, color: str) -> Any:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    return solid(shape, color)
