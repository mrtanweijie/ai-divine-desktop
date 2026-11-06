"""海报排版（Pillow 合成文案层）。

为什么不让模型直接画字：图像模型对中文长句的渲染不稳定（错字/缺笔/脏字），
商品名与卖点又必须**一字不差**。所以底图交给模型（只出画面、不出文字），
文案层在这里用系统中文字体合成——文字 100% 可控，也不受模型抖动影响。

排版语言（与产品整体一致，极简黑白）：
  底部 42% 高的黑色渐变遮罩 → 主标题（商品名）→ 细分割线 → 卖点列表；
  全部左对齐、左内距 = 画布宽度的 6.7%，不叠加任何装饰色块。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: 输出画布的短边基准（1080 宽，长边按比例算）
CANVAS_SHORT_SIDE = 1080

#: 比例 → (宽, 高)；未命中的比例按 3:4 处理
_RATIO_SIZES: dict[str, tuple[int, int]] = {
    "3:4": (1080, 1440),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:3": (1440, 1080),
    "16:9": (1920, 1080),
}

#: 字体候选：macOS 上优先冬青黑体（简中字形完整），再退系统黑体/宋体
_FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino Sans GB"),
    ("/System/Library/Fonts/STHeiti Medium.ttc", "Heiti"),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", "Songti"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "Arial Unicode"),
)


@dataclass(frozen=True)
class PosterText:
    """海报文案。`title` 必填，`points` 最多取前 4 条。"""

    title: str
    points: list[str]


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """按字号加载中文字体；`bold` 时优先选同族更粗的 face。

    `.ttc` 是字体集合，不同 index 对应不同 weight（如冬青 W3 / W6）。
    """
    preferred = ("W6", "W5", "Medium", "Bold", "W3") if bold else ("W3", "W6", "Medium")
    for path, family in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        best: tuple[int, ImageFont.FreeTypeFont] | None = None
        for index in range(0, 8):
            try:
                font = ImageFont.truetype(path, size, index=index)
            except OSError:
                break
            name = " ".join(part for part in font.getname() if part)
            if family.split()[0] not in name:
                continue
            rank = next(
                (len(preferred) - i for i, key in enumerate(preferred) if key in name), 0
            )
            if best is None or rank > best[0]:
                best = (rank, font)
            if rank == len(preferred):  # 已经是首选 weight
                break
        if best:
            return best[1]
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # 兜底：Pillow 自带位图字体（中文会缺字，但至少不崩）
    return ImageFont.load_default(size=size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度断行：中文逐字、西文按词，超长单行不做二次拆分。"""
    text = " ".join(text.split())
    if not text:
        return []

    def width_of(candidate: str) -> int:
        return int(font.getlength(candidate))

    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and width_of(candidate) > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.rstrip())
    return lines


def _ellipsize(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """单行截断：放不下就用「…」收尾（不硬切半个字）。"""
    if int(font.getlength(text)) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and int(font.getlength(trimmed + ellipsis)) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比裁切填满目标尺寸（不拉伸变形）。"""
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    resized = image.resize(
        (max(1, round(src_w * scale)), max(1, round(src_h * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _paint_scrim(canvas: Image.Image, height_ratio: float = 0.44) -> None:
    """底部黑色渐变遮罩：保证白字在任何底图上都读得清。"""
    width, height = canvas.size
    scrim_height = int(height * height_ratio)
    top = height - scrim_height
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for offset in range(scrim_height):
        # 二次曲线：上缘更淡，往下快速加厚，文字区稳定在 0.86
        progress = offset / max(1, scrim_height - 1)
        alpha = int(255 * 0.86 * (progress**1.6))
        draw.line([(0, top + offset), (width, top + offset)], fill=(0, 0, 0, alpha))
    canvas.alpha_composite(overlay)


def canvas_size(aspect_ratio: str) -> tuple[int, int]:
    """比例 → 输出尺寸（未知比例回落 3:4）。"""
    return _RATIO_SIZES.get((aspect_ratio or "").strip(), _RATIO_SIZES["3:4"])


def compose(
    base_image: Path,
    text: PosterText,
    out_path: Path,
    *,
    aspect_ratio: str = "3:4",
) -> Path:
    """把文案合成到底图上，写出成品海报（PNG）。

    文案区高度不够时**逐级收缩**（字号 → 卖点条数），保证永远不压到画面主体、
    也不抛异常——商品名往往比示例长，硬 assert 会让生成在最后一步失败。
    """
    size = canvas_size(aspect_ratio)
    width, height = size

    with Image.open(base_image) as raw:
        canvas = _cover(raw.convert("RGB"), size).convert("RGBA")

    _paint_scrim(canvas)

    margin = int(width * 0.067)
    max_text_width = width - margin * 2
    points = [item.strip() for item in text.points if item and item.strip()][:4]
    bottom_padding = int(height * 0.052)
    # 文案区顶边不得高于此线（再高就会压住商品主体）
    min_title_top = int(height * 0.24)

    layout: tuple[int, list[str], list[str], int, int] | None = None
    for shrink in (1.0, 0.92, 0.84, 0.76):
        title_size = max(28, int(width * 0.082 * shrink))
        point_size = max(20, int(width * 0.037 * shrink))
        title_font = _load_font(title_size, bold=True)
        point_font = _load_font(point_size)

        wrapped = _wrap(text.title, title_font, max_text_width)
        title_lines = wrapped[:2]
        if len(wrapped) > 2:
            title_lines[-1] = _ellipsize(wrapped[1] + "…", title_font, max_text_width)
        title_line_height = int(title_font.size * 1.24)

        point_blocks = [
            _ellipsize(point, point_font, max_text_width - point_size) for point in points
        ]
        point_line_height = int(point_font.size * 1.62)
        point_gap = int(point_font.size * 0.62)
        divider_gap = int(title_font.size * 0.42)
        divider_height = max(2, int(height * 0.0016))

        # 卖点从 4 条往下砍，直到文案区不侵入主体
        for keep in range(len(point_blocks), -1, -1):
            kept = point_blocks[:keep]
            points_height = len(kept) * point_line_height
            if kept:
                points_height += (len(kept) - 1) * point_gap
            title_height = len(title_lines) * title_line_height
            divider_total = (divider_gap * 2 + divider_height) if kept else 0
            title_top = (
                height
                - bottom_padding
                - points_height
                - divider_total
                - title_height
            )
            if title_top >= min_title_top:
                layout = (title_line_height, title_lines, kept, point_line_height, point_gap)
                layout_metrics = (title_font, point_font, divider_gap, divider_height)
                break
        if layout:
            break

    if layout is None:
        # 极端兜底：只画标题，字号最小档
        title_font = _load_font(max(24, int(width * 0.06)), bold=True)
        point_font = title_font
        title_lines = _wrap(text.title, title_font, max_text_width)[:2]
        layout = (int(title_font.size * 1.24), title_lines, [], 0, 0)
        layout_metrics = (title_font, point_font, 0, 0)

    title_line_height, title_lines, point_blocks, point_line_height, point_gap = layout
    title_font, point_font, divider_gap, divider_height = layout_metrics

    draw = ImageDraw.Draw(canvas)
    cursor_bottom = height - bottom_padding

    # 卖点：自下而上绘制，天然与底部留白对齐
    point_bottom = cursor_bottom
    for block in reversed(point_blocks):
        draw.text(
            (margin, point_bottom - point_line_height),
            block,
            font=point_font,
            fill=(255, 255, 255, 226),
        )
        point_bottom -= point_line_height + point_gap

    if point_blocks:
        divider_y = point_bottom - divider_gap
        draw.rectangle(
            [
                (margin, divider_y),
                (margin + int(width * 0.086), divider_y + divider_height),
            ],
            fill=(255, 255, 255, 150),
        )
        title_bottom = divider_y - divider_gap
    else:
        title_bottom = point_bottom

    for index, line in enumerate(reversed(title_lines)):
        draw.text(
            (margin, title_bottom - title_line_height * (index + 1)),
            line,
            font=title_font,
            fill=(255, 255, 255, 255),
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, format="PNG", optimize=True)
    return out_path
