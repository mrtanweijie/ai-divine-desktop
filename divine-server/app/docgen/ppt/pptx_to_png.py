"""pptx -> PNG 渲染（无 LibreOffice 环境下的视觉预览）。

直接读取 pptx 的形状 XML（位置 / 填充 / 渐变 / 透明度 / 文字 / 图表数据），
用 Pillow 重绘为位图。对位 `docgen/pdf/preview.py` 的角色：PDF 用 PyMuPDF
把页面转成 PNG data URL，PPT 用本模块把幻灯片转成 PNG data URL，前端因此
能把 PPT 渲染成页面图片而不是抽取出的纯文本。

限制（有意为之，够用于预览）：
- 文字按 run 逐段绘制，不处理字符间距 / 行距微调；
- 图表 / 表格画占位框 + 数据摘要 + 数据点色板（色板用于验证主题 palette 传导）；
- 不处理图片填充（PICTURE 形状画占位框）。

用法（脚本）：见 `app/tools/scripts/pptx_to_png.py`。
"""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

MAX_PPTX_PREVIEW_PAGES = 20
MAX_PPTX_PREVIEW_BYTES = 30 * 1024 * 1024
# 1.5 × 96dpi = 144dpi：16:9 幻灯片得 2000×1125，面板内放大到 retina 仍清晰
PPTX_RENDER_SCALE = 1.5
BASE_DPI = 96.0

EMU_PER_IN = 914400

# 中文字体候选（macOS 优先，Linux 容器兜底）
_FONT_CANDIDATES: list[tuple[str, int]] = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
]

_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def _font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (max(8, int(size_px)), bold)
    if key in _font_cache:
        return _font_cache[key]
    candidates = list(reversed(_FONT_CANDIDATES)) if not bold else _FONT_CANDIDATES
    for path, index in candidates:
        try:
            resolved = ImageFont.truetype(path, key[0], index=index)
        except Exception:  # noqa: BLE001 — 逐个候选尝试，缺失即跳过
            continue
        _font_cache[key] = resolved
        return resolved
    resolved = ImageFont.load_default()
    _font_cache[key] = resolved
    return resolved


def _hex(color: Any) -> str:
    try:
        return str(color.rgb)
    except Exception:  # noqa: BLE001
        return "000000"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _alpha_of(shape: Any) -> int:
    """读取纯色填充上的 a:alpha（0-255）。无则 255。"""
    try:
        solid = shape.fill._xPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill"
        )
        if solid is None:
            return 255
        srgb = solid.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr"
        )
        if srgb is None:
            return 255
        alpha = srgb.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}alpha"
        )
        if alpha is None:
            return 255
        return max(0, min(255, round(int(alpha.get("val")) / 100000 * 255)))
    except Exception:  # noqa: BLE001
        return 255


def _fill(shape: Any) -> tuple[Any, ...]:
    """返回 ('solid', hex, alpha) / ('grad', [(pos,hex)...], angle) / ('none',)"""
    try:
        fill_type = shape.fill.type
    except Exception:  # noqa: BLE001
        return ("none",)
    if fill_type == 1:  # MSO_FILL.SOLID
        return ("solid", _hex(shape.fill.fore_color), _alpha_of(shape))
    if fill_type == 3:  # MSO_FILL.GRADIENT
        try:
            stops = [(s.position, _hex(s.color)) for s in shape.fill.gradient_stops]
        except Exception:  # noqa: BLE001
            return ("none",)
        try:
            angle = float(shape.fill.gradient_angle)
        except Exception:  # noqa: BLE001
            angle = 0.0
        return ("grad", stops, angle)
    return ("none",)


def _line(shape: Any, dpi: float) -> tuple[str, float] | None:
    try:
        if shape.line.fill.type != 1:  # MSO_FILL.SOLID
            return None
        color = _hex(shape.line.color)
        try:
            width = float(shape.line.width.pt) * dpi / 72.0
        except Exception:  # noqa: BLE001
            width = 1.0
        return (color, max(0.5, width))
    except Exception:  # noqa: BLE001
        return None


def _rect_px(shape: Any, dpi: float) -> tuple[float, float, float, float]:
    return (
        shape.left / EMU_PER_IN * dpi,
        shape.top / EMU_PER_IN * dpi,
        shape.width / EMU_PER_IN * dpi,
        shape.height / EMU_PER_IN * dpi,
    )


def _star_points(x: float, y: float, w: float, h: float, points: int,
                 inner: float = 0.24) -> list[tuple[float, float]]:
    """n 角星顶点（外角与内角交替）。"""
    cx, cy = x + w / 2.0, y + h / 2.0
    rx, ry = w / 2.0, h / 2.0
    step = math.pi / points
    start = -math.pi / 2 if points in (4, 5) else 0.0
    result: list[tuple[float, float]] = []
    for i in range(points * 2):
        angle = start + step * i
        k = 1.0 if i % 2 == 0 else inner
        result.append((cx + math.cos(angle) * rx * k,
                       cy + math.sin(angle) * ry * k))
    return result


def _grad_color(stops: list[tuple[float, str]], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    stops = sorted(stops, key=lambda s: s[0])
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            span = (p1 - p0) or 1.0
            k = (t - p0) / span
            a, b = _rgb(c0), _rgb(c1)
            return tuple(round(a[j] + (b[j] - a[j]) * k) for j in range(3))  # type: ignore[return-value]
    return _rgb(stops[0 if t < 0.5 else -1][1])


_SHAPE_KIND_STAR = {4: "STAR_4_POINT", 5: "STAR_5_POINT"}


def _paint_shape(base: Image.Image, shape: Any, dpi: float,
                 draw_text_fn: Callable[[], None]) -> None:
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE

    try:
        shape_type = shape.shape_type
    except Exception:  # noqa: BLE001
        shape_type = None
    if shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
        draw_text_fn()
        return
    if shape_type != MSO_SHAPE_TYPE.AUTO_SHAPE:
        if shape.has_text_frame:
            draw_text_fn()
        return

    try:
        kind = shape.auto_shape_type
    except Exception:  # noqa: BLE001
        kind = None

    x, y, w, h = _rect_px(shape, dpi)
    if w <= 0 or h <= 0:
        return

    is_round = kind == MSO_SHAPE.ROUNDED_RECTANGLE
    is_oval = kind == MSO_SHAPE.OVAL
    star_count = 0
    if kind is not None:
        for count, name in _SHAPE_KIND_STAR.items():
            if getattr(MSO_SHAPE, name, None) == kind:
                star_count = count
                break

    radius = 0.0
    if is_round:
        try:
            radius = float(shape.adjustments[0]) * min(w, h)
        except Exception:  # noqa: BLE001
            radius = 0.08 * min(w, h)

    fill = _fill(shape)
    if fill[0] != "none":
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        if fill[0] == "solid":
            rgba = _rgb(fill[1]) + (fill[2],)
            box = [x, y, x + w, y + h]
            if is_oval:
                ld.ellipse(box, fill=rgba)
            elif star_count:
                ld.polygon(_star_points(x, y, w, h, star_count), fill=rgba)
            elif is_round:
                ld.rounded_rectangle(box, radius=radius, fill=rgba)
            else:
                ld.rectangle(box, fill=rgba)
        else:
            _, stops, angle = fill
            vertical = 80 <= (angle % 180) <= 100
            span = h if vertical else w
            steps = max(2, int(span))
            for i in range(steps):
                t = i / (steps - 1)
                color = _grad_color(stops, t) + (255,)
                if vertical:
                    ld.line([(x, y + i), (x + w, y + i)], fill=color, width=1)
                else:
                    ld.line([(x + i, y), (x + i, y + h)], fill=color, width=1)
            if is_oval or is_round or star_count:
                mask = Image.new("L", base.size, 0)
                md = ImageDraw.Draw(mask)
                box = [x, y, x + w, y + h]
                if is_oval:
                    md.ellipse(box, fill=255)
                elif is_round:
                    md.rounded_rectangle(box, radius=radius, fill=255)
                else:
                    md.polygon(_star_points(x, y, w, h, star_count), fill=255)
                layer.putalpha(Image.composite(layer.getchannel("A"),
                                               Image.new("L", base.size, 0), mask))
        base.alpha_composite(layer)

    outline = _line(shape, dpi)
    if outline:
        color, width = outline
        ld = ImageDraw.Draw(base)
        box = [x, y, x + w, y + h]
        try:
            if is_oval:
                ld.ellipse(box, outline=_rgb(color) + (255,),
                           width=max(1, round(width)))
            else:
                ld.rectangle(box, outline=_rgb(color) + (255,),
                             width=max(1, round(width)))
        except Exception:  # noqa: BLE001
            pass

    if shape.has_text_frame:
        draw_text_fn()


def _draw_text(base: Image.Image, shape: Any, dpi: float) -> None:
    """按段落绘制文字；同段多个 run 排在同一行（数字强调色依赖此行为）。"""
    text_frame = shape.text_frame
    x, y, w, _ = _rect_px(shape, dpi)
    drawer = ImageDraw.Draw(base)
    cursor_y = float(y)
    for para in text_frame.paragraphs:
        segments: list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]] = []
        for run in para.runs:
            if not run.text:
                continue
            size_pt = run.font.size.pt if run.font.size else 18.0
            font = _font(size_pt * dpi / 72.0, bool(run.font.bold))
            segments.append((run.text, font, _rgb(_hex(run.font.color))))
        if not segments:
            cursor_y += 10 * dpi / BASE_DPI
            continue
        limit = max(8.0, w)
        lines: list[list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]]] = []
        current: list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]] = []
        width_used = 0.0
        for text, font, color in segments:
            for char in text:
                char_w = font.getlength(char)
                if current and width_used + char_w > limit:
                    lines.append(current)
                    current = []
                    width_used = 0.0
                current.append((char, font, color))
                width_used += char_w
        if current:
            lines.append(current)

        max_px = max(seg[1].size for seg in segments)
        line_h = max_px * 1.32
        try:
            align = str(para.alignment)
        except Exception:  # noqa: BLE001
            align = "LEFT (1)"

        for line in lines:
            line_w = sum(font.getlength(char) for char, font, _ in line)
            if "CENTER" in align:
                pen_x = x + (w - line_w) / 2
            elif "RIGHT" in align:
                pen_x = x + w - line_w
            else:
                pen_x = x
            ascent, descent = line[0][1].getmetrics()
            baseline_y = cursor_y + (line_h - (ascent + descent)) / 2
            for char, font, color in line:
                drawer.text((pen_x, baseline_y), char, font=font,
                            fill=color + (255,))
                pen_x += font.getlength(char)
            cursor_y += line_h


def _draw_graphic_frame(base: Image.Image, shape: Any, dpi: float) -> None:
    """图表画占位框 + 数据摘要；表格直接绘制行内容（预览即所得，避免空框误导）。"""
    x, y, w, h = _rect_px(shape, dpi)
    drawer = ImageDraw.Draw(base)
    drawer.rectangle([x, y, x + w, y + h], outline=(206, 200, 216, 255), width=1)
    if getattr(shape, "has_table", False):
        try:
            tbl = shape.table
            n_cols = len(tbl.columns)
            n_rows = max(len(tbl.rows), 1)
            row_h = max(18 * dpi / BASE_DPI, h / n_rows)
            col_w = w / n_cols
            # 先铺单元格底色（含暗色主题深底），按填充亮度自适应文字颜色
            fills: list[list[tuple[int, int, int] | None]] = []
            for r_i in range(n_rows):
                row_fills: list[tuple[int, int, int] | None] = []
                for c_i in range(n_cols):
                    rgbv = None
                    try:
                        color = str(tbl.cell(r_i, c_i).fill.fore_color.rgb)
                        rgbv = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
                    except Exception:  # noqa: BLE001 — 无填充跳过
                        pass
                    row_fills.append(rgbv)
                    if rgbv:
                        drawer.rectangle(
                            [x + c_i * col_w, y + r_i * row_h,
                             x + (c_i + 1) * col_w, y + (r_i + 1) * row_h],
                            fill=rgbv + (255,))
                fills.append(row_fills)
            for r_i, _row in enumerate(tbl.rows):
                cy = y + r_i * row_h
                if cy > y + h - 4:
                    break
                for c_i in range(n_cols):
                    text = tbl.cell(r_i, c_i).text.replace("\n", " ")[:24]
                    fill = fills[r_i][c_i] if r_i < len(fills) \
                        and c_i < len(fills[r_i]) else None
                    if fill is not None:
                        # 按填充亮度选字色：暗底白字 / 亮底深字
                        lum = (0.299 * fill[0] + 0.587 * fill[1]
                               + 0.114 * fill[2])
                        t_fill = ((255, 255, 255, 255) if lum < 128
                                  else (30, 32, 38, 255))
                    else:
                        t_fill = ((30, 32, 38, 255) if r_i == 0
                                  else (70, 74, 82, 255))
                    cx = x + c_i * col_w + 8 * dpi / BASE_DPI
                    drawer.text((cx, cy + 6 * dpi / BASE_DPI), text,
                                font=_font(12 if r_i else 12.5), fill=t_fill)
                if r_i == 0:
                    drawer.line([x, cy + row_h, x + w, cy + row_h],
                                fill=(206, 200, 216, 255), width=1)
            return
        except Exception:  # noqa: BLE001 — 摘要失败退回标签
            pass
    label = "[table]" if getattr(shape, "has_table", False) else "[graphic]"
    swatches: list[str] = []
    if getattr(shape, "has_chart", False):
        try:
            chart = shape.chart
            plot = chart.plots[0]
            cats = [str(c) for c in plot.categories]
            values = list(chart.series[0].values)
            label = (f"[chart {str(chart.chart_type).split('(')[0].strip()}] "
                     + "  ".join(f"{c}:{v}" for c, v in zip(cats, values)))[:150]
            try:
                swatches = [str(dp.format.fill.fore_color.rgb)
                            for dp in plot.series[0].points]
            except Exception:  # noqa: BLE001
                try:
                    swatches = [str(s.format.fill.fore_color.rgb)
                                for s in chart.series]
                except Exception:  # noqa: BLE001
                    swatches = []
        except Exception as exc:  # noqa: BLE001
            label = f"[chart err: {type(exc).__name__}]"

    drawer.text((x + 10, y + 10), label, font=_font(13),
                fill=(90, 90, 110, 255))
    swatch_h = 16 * dpi / BASE_DPI
    for i, color in enumerate(swatches[:10]):
        box = [x + 10 + i * (swatch_h + 14), y + h - swatch_h - 10,
               x + 10 + swatch_h + i * (swatch_h + 14), y + h - 10]
        drawer.rectangle(box, fill=_rgb(color) + (255,))


def _render_slide(base: Image.Image, slide: Any, dpi: float) -> None:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    def walk(shapes: Any) -> None:
        for shape in shapes:
            try:
                shape_type = shape.shape_type
                if shape_type == MSO_SHAPE_TYPE.GROUP:
                    walk(shape.shapes)
                    continue
                if shape_type in (MSO_SHAPE_TYPE.CHART, MSO_SHAPE_TYPE.TABLE,
                                  MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT,
                                  MSO_SHAPE_TYPE.LINKED_OLE_OBJECT) \
                        or getattr(shape, "has_chart", False) \
                        or getattr(shape, "has_table", False):
                    _draw_graphic_frame(base, shape, dpi)
                    continue
                _paint_shape(base, shape, dpi,
                             lambda s=shape: _draw_text(base, s, dpi))
            except Exception as exc:  # noqa: BLE001 — 单个形状失败不拖垮整页
                logger.debug("slide shape skipped: %s: %s", type(exc).__name__, exc)

    walk(slide.shapes)


def _open_presentation(path: Path) -> Any:
    from pptx import Presentation

    if path.suffix.lower() not in (".pptx", ".ppsx"):
        raise RuntimeError("pptx 预览只支持 .pptx / .ppsx（旧版 .ppt 请先转换）")
    try:
        return Presentation(str(path))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"PPT 文件损坏或格式不支持: {exc}") from exc


def render_pptx_page_images(path: Path, scale: float = PPTX_RENDER_SCALE,
                            page: int | None = None
                            ) -> list[tuple[int, Image.Image]]:
    """把 pptx 渲染成 PIL Image 列表，返回 [(页码, 图片), ...]。

    页码从 1 起，按演示文稿实际尺寸渲染（非固定 16:9）；page 传 1 基页码
    只渲染那一页（导出单页时省掉整本的开销）。
    """
    prs = _open_presentation(Path(path))
    width_in = prs.slide_width / EMU_PER_IN
    height_in = prs.slide_height / EMU_PER_IN
    if width_in <= 0 or height_in <= 0:
        raise RuntimeError("演示文稿页面尺寸异常")
    dpi = BASE_DPI * scale
    slides = list(prs.slides)
    if not slides:
        raise RuntimeError("演示文稿没有任何页面")
    if page is not None:
        if page < 1 or page > len(slides):
            raise RuntimeError(f"页码超出范围: 1-{len(slides)}")
        selected = [(page, slides[page - 1])]
    else:
        selected = list(enumerate(slides, start=1))
    results: list[tuple[int, Image.Image]] = []
    for number, slide in selected:
        canvas = Image.new("RGBA",
                           (int(width_in * dpi), int(height_in * dpi)),
                           (255, 255, 255, 255))
        _render_slide(canvas, slide, dpi)
        flat = Image.new("RGB", canvas.size, (255, 255, 255))
        flat.paste(canvas, mask=canvas.getchannel("A"))
        results.append((number, flat))
    return results


def render_pptx_pages(path: Path, max_pages: int = MAX_PPTX_PREVIEW_PAGES,
                      scale: float = PPTX_RENDER_SCALE) -> list[str]:
    """返回至多 max_pages 页的 PNG data URL（与 render_pdf_pages 对位）。"""
    images = render_pptx_page_images(Path(path), scale)
    pages: list[str] = []
    for _, image in images[:max(1, max_pages)]:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        pages.append(f"data:image/png;base64,{encoded}")
    return pages


def render_pptx_to_files(path: Path, outdir: Path,
                         scale: float = PPTX_RENDER_SCALE,
                         page: int | None = None) -> list[Path]:
    """把 pptx 每页渲染成 PNG 文件，返回文件路径列表（供工具落盘）。"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem or "slides"
    outputs: list[Path] = []
    for number, image in render_pptx_page_images(Path(path), scale, page):
        target = outdir / f"{stem}-{number:02d}.png"
        image.save(target, format="PNG", optimize=True)
        outputs.append(target)
    return outputs
