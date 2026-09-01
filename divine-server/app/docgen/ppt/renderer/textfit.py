"""排版自适应：按字符量与目标框尺寸估算并挑选字号。

CJK 字符按全角（1.0 em）估宽，拉丁/数字按 0.55 em；
在候选字号序列里从大到小找到第一个能放下目标框的组合。
"""

from __future__ import annotations

import math


def _is_wide(ch: str) -> bool:
    code = ord(ch)
    return (
        0x2E80 <= code <= 0x9FFF      # CJK 部首 / 汉字
        or 0xF900 <= code <= 0xFAFF   # 兼容表意文字
        or 0xFF00 <= code <= 0xFF60   # 全角标点
        or 0x3000 <= code <= 0x303F   # CJK 符号
    )


def text_em_width(text: str) -> float:
    return sum(1.0 if _is_wide(ch) else 0.55 for ch in text)


def wrapped_lines(text: str, width_in: float, size_pt: float) -> int:
    """估算文本在指定宽度、字号下折行后的总行数。"""
    if not text:
        return 0
    em_per_line = max((width_in * 72.0) / size_pt, 1.0)
    total = 0
    for para in text.split("\n"):
        total += max(1, math.ceil(text_em_width(para) / em_per_line))
    return total


def fits(text: str, width_in: float, height_in: float, size_pt: float,
         line_spacing: float = 1.2, space_after_pt: float = 0.0,
         pad_in: float = 0.06) -> bool:
    lines = wrapped_lines(text, width_in, size_pt)
    used = lines * size_pt * line_spacing / 72.0 + space_after_pt / 72.0
    return used <= height_in - pad_in


def pick_size(text: str, width_in: float, height_in: float,
              candidates: list[float], **kwargs: float) -> float:
    """从候选字号（从大到小）里选第一个放得下的；都放不下返回最小档。"""
    for size in candidates:
        if fits(text, width_in, height_in, size, **kwargs):
            return size
    return candidates[-1]


def split_title_desc(point: str) -> tuple[str, str]:
    """把 "标题|描述" 形式的要点拆成 (标题, 描述)；无分隔符时描述为空。"""
    text = (point or "").strip()
    for sep in ("|", "：", ": "):
        if sep in text:
            head, _, rest = text.partition(sep)
            return head.strip(), rest.strip()
    return text, ""
