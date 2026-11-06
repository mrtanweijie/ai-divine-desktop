"""海报底图提示词构造。

底图只负责「画面」：商品主体、光影、场景、留白。**一个字都不让模型写**——
中文文案由 `layout.compose` 用系统字体叠上去（模型写中文必错字）。
"""

from __future__ import annotations

#: 风格 → 画面语言（模型能理解的具体描述，不写「好看」这类空词）
STYLE_PRESETS: dict[str, str] = {
    "clean": (
        "极简商业摄影风格：干净的单色或低饱和渐变背景，柔和均匀的棚拍光，"
        "主体居中偏上，四周大量干净留白，画面克制、通透、有呼吸感"
    ),
    "promo": (
        "促销广告风格：高饱和暖色灯光与硬朗阴影，画面有强烈视觉冲击力与食欲感，"
        "主体占据画面中心偏下，背景干净不杂乱"
    ),
    "premium": (
        "高级质感风格：低调深色背景，侧逆光勾勒轮廓，细微的材质反光与景深虚化，"
        "整体沉静、昂贵、有杂志大片感"
    ),
}

#: 比例 → 构图提示（竖版要强调上下留白）
_RATIO_HINTS: dict[str, str] = {
    "3:4": "竖版 3:4 构图",
    "9:16": "竖版 9:16 构图",
    "1:1": "方形 1:1 构图",
    "4:3": "横版 4:3 构图",
    "16:9": "横版 16:9 构图",
}

STYLE_LABELS: dict[str, str] = {
    "clean": "简约留白",
    "promo": "促销冲击",
    "premium": "高级质感",
}

_COMMON_SUFFIX = (
    "画面底部约 40% 保持干净、低信息量（纯色或柔和渐变的背景延伸），"
    "不要出现任何文字、字母、数字、水印、logo、标签、价签、包装上的印刷字。"
)


def build_prompt(
    *,
    product_name: str,
    selling_points: list[str],
    style: str,
    aspect_ratio: str,
    extra: str = "",
) -> str:
    """拼底图提示词。

    卖点转成**画面元素**（而不是文字）——例如「现做现卖」→ 新鲜食材与手作动作，
    让模型有事可画；文案会在合成阶段另行绘制。
    """
    style_text = STYLE_PRESETS.get(style, STYLE_PRESETS["clean"])
    hint = _RATIO_HINTS.get(aspect_ratio, "竖版 3:4 构图")

    elements = "、".join(item.strip() for item in selling_points if item.strip())
    subject = f"商品主体：{product_name.strip()}" if product_name.strip() else "商品主体"
    if elements:
        subject += f"，画面元素体现这些卖点：{elements}"

    parts = [
        "拍摄一张用于商品海报的高质量照片。",
        f"{subject}。",
        f"{style_text}。",
        f"{hint}，主体完整不出画。",
        extra.strip(),
        _COMMON_SUFFIX,
    ]
    return "".join(part for part in parts if part)
