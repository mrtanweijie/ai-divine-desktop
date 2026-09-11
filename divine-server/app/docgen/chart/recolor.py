"""图表 SVG 主题色重着色：让 PDF 内嵌图表跟随文档主题色。

图表 SVG（docgen/chart/svg.py）生成时使用固定色板 COLORS，与 PDF 主题无关，
深蓝商务主题配奶油金柱子观感割裂。本模块在 PDF 渲染时把 SVG 里的已知色板
hex 替换为从主题主色派生的系列色板；只触碰色板内的精确色值，中性色
（标题/轴/网格）与其它 SVG 插图不受影响。
"""

from __future__ import annotations

import base64
import colorsys
import re
from pathlib import Path

from ..pdf.theme_colors import resolve_color as _resolve_color

from .svg import COLORS

# 图表固定色板（svg.py COLORS，保持顺序），供精确匹配替换
_CHART_PALETTE = [color.upper() for color in COLORS]

# 非色板色（中性色/任意自定义色）不会被替换，这里仅用于文档说明
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def _resolve_rgb(value: str) -> tuple[int, int, int] | None:
    # 复用主题色的统一解析（#hex / rgb() / 颜色名）
    return _resolve_color(value)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02X%02X%02X" % tuple(round(channel * 255) for channel in rgb)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def derive_series_palette(primary_color: str) -> dict[str, str] | None:
    """从主题主色派生 9 色系列色板，与 COLORS 顺序一一对应。

    派生策略：第 1 色即主色（亮度压到图表填充可读区间），其余按
    亮度阶梯 + 邻近色相旋转展开，保证多系列可区分且整体协调；
    低饱和主色（黑白主题）自然退化为灰度阶梯。
    无法解析主色时返回 None。
    """
    rgb = _resolve_rgb(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    saturation = _clamp(saturation, 0.0, 0.75)
    base_l = _clamp(lightness, 0.38, 0.58)

    def variant(hue_shift: float, l_delta: float) -> str:
        return _rgb_to_hex(
            colorsys.hls_to_rgb(
                (hue + hue_shift) % 1.0,
                _clamp(base_l + l_delta, 0.22, 0.78),
                saturation,
            )
        )

    derived = [
        variant(0.0, 0.0),
        variant(0.0, 0.16),
        variant(-0.045, 0.04),
        variant(0.0, 0.30),
        variant(0.055, -0.06),
        variant(0.055, 0.10),
        variant(0.0, -0.12),
        variant(-0.045, 0.24),
        variant(0.11, 0.06),
    ]
    return dict(zip(_CHART_PALETTE, derived))


def recolor_chart_svg(svg_text: str, palette: dict[str, str]) -> str:
    """把 SVG 文本中图表色板 hex 替换为主题派生色（大小写不敏感）。"""
    result = svg_text
    for old, new in palette.items():
        result = re.sub(
            re.escape(old), new, result, flags=re.IGNORECASE
        )
    return result


_IMG_SVG_RE = re.compile(
    r'<img[^>]*src="([^"]+\.svg)"[^>]*>', re.IGNORECASE
)
_INLINE_SVG_RE = re.compile(r"(<svg[^>]*>.*?</svg>)", re.DOTALL)


def recolor_body_svg(
    body: str,
    primary_color: str | None,
    base_dir: Path | None = None,
) -> str:
    """重着色 HTML body 里的图表：内联 SVG 直接替换，`<img src="*.svg">`
    读取本地文件重着色后转为 data URI 内嵌。主色缺失或不可解析时原样返回。
    """
    if not primary_color:
        return body
    palette = derive_series_palette(primary_color)
    if not palette:
        return body

    def replace_inline(match: re.Match[str]) -> str:
        return recolor_chart_svg(match.group(1), palette)

    body = _INLINE_SVG_RE.sub(replace_inline, body)

    def replace_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        src = match.group(1)
        if src.lower().startswith(("data:", "http://", "https://")):
            return tag
        path = Path(src)
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / src
        try:
            svg_text = path.read_text(encoding="utf-8")
        except OSError:
            return tag
        recolored = recolor_chart_svg(svg_text, palette)
        encoded = base64.b64encode(recolored.encode("utf-8")).decode("ascii")
        return tag.replace(src, f"data:image/svg+xml;base64,{encoded}")

    return _IMG_SVG_RE.sub(replace_img, body)
