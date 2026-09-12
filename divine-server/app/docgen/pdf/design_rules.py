"""场景 → 主题/配色/封面/目录 的确定性设计决策层。

在 Agent 未显式指定风格时，根据用户输入（场景关键词 + 风格词）自动决策，
保证生成 PDF 的主题与内容类型匹配；用户/Agent 显式指定时以显式值为准。

优先级链：显式参数 > prompt 风格词 > DesignSpec（LLM 设计师）> 场景分类 > 配方默认。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .theme_manager import resolve_color

# ---------------------------------------------------------------------------
# 已知主题 / 配色（与 pdf_theme_manager.THEMES、渲染器保持一致）
# ---------------------------------------------------------------------------
KNOWN_THEMES: frozenset[str] = frozenset(
    {
        "universal",
        "resume",
        "notion",
        "linear",
        "apple",
        "modern",
        "academic",
        "travel",
        "travel_mag",
        "travel_swiss",
        "travel_bento",
        "travel_aurora",
        "roadmap",
        "minimal",
    }
)

KNOWN_COLOR_SCHEMES: frozenset[str] = frozenset(
    {
        "teal",
        "blue",
        "green",
        "warm",
        "monochrome",
        "purple",
        "iceblue",
        "desert",
        "vintage",
        "midnight",
        "pureblack",
        "mistsage",
        "mistblue",
        "duskmauve",
        "lotuspink",
        "dunesand",
        "smokegray",
    }
)

# 兼容旧 style 参数的映射（无对应主题的 style 回退 universal）
STYLE_TO_THEME: dict[str, str] = {
    "modern": "modern",
    "academic": "academic",
    "corporate": "universal",
    "minimal": "minimal",
    "playful": "universal",
}

# ---------------------------------------------------------------------------
# 场景配置表
# ---------------------------------------------------------------------------
# 命中多个场景时按 SCENE_PRIORITY 取前面的（客户/高管场景优先于内部场景）
SCENE_PRIORITY: list[str] = [
    "proposal",
    "quarterly",
    "business",
    "prd",
    "portfolio",
    "editorial",
    "weekly",
]

SCENES: dict[str, dict[str, Any]] = {
    "weekly": {
        "keywords": (
            "周报",
            "日报",
            "站会",
            "晨会",
            "本周",
            "上周",
            "weekly",
            "sprint",
            "standup",
        ),
        "theme": "minimal",
        "color_scheme": "monochrome",
        "cover": True,
        "toc": False,
        "cover_style": "minimal",
        "description": "团队周报/日报：极简黑白，一眼扫完",
    },
    "quarterly": {
        "keywords": (
            "季度",
            "月报",
            "汇报",
            "总结",
            "述职",
            "高管",
            "领导",
            "老板",
            "vp",
            "cto",
            "review",
            "q1",
            "q2",
            "q3",
            "q4",
        ),
        "theme": "universal",
        "color_scheme": "blue",
        "cover": True,
        "toc": True,
        "cover_style": "split",
        "description": "季度/月度汇报：商务稳重，深蓝",
    },
    "proposal": {
        "keywords": (
            "提案",
            "方案",
            "客户",
            "报价",
            "合作",
            "投标",
            "建议书",
            "商务",
            "pitch",
        ),
        "theme": "modern",
        "color_scheme": "blue",
        "cover": True,
        "toc": True,
        "cover_style": "left-aligned",
        "description": "客户提案/技术方案：科技感蓝灰",
    },
    "business": {
        "keywords": (
            "商业分析",
            "商业模式",
            "商业计划",
            "商业报告",
            "经营分析",
            "商业画布",
            "品牌分析",
            "品牌战略",
            "品牌诊断",
            "品牌定位",
            "竞品",
            "对标",
            "护城河",
            "私域",
            "联名",
            "增长策略",
        ),
        "theme": "universal",
        "color_scheme": "blue",
        "cover": True,
        "toc": True,
        "cover_style": "split",
        "description": "商业分析报告：咨询风格，蓝灰稳重",
    },
    "portfolio": {
        "keywords": (
            "作品集",
            "个人展示",
            "自我介绍",
            "作品",
            "portfolio",
            "showcase",
        ),
        "theme": "apple",
        "color_scheme": "blue",
        "cover": True,
        "toc": False,
        "cover_style": "hero-graphic",
        "description": "作品集/个人展示：大圆角舒适",
    },
    "prd": {
        "keywords": (
            "prd",
            "需求文档",
            "技术文档",
            "api",
            "接口文档",
            "验收",
            "迭代",
            "产品需求",
            "spec",
        ),
        "theme": "linear",
        "color_scheme": "blue",
        "cover": True,
        "toc": True,
        "cover_style": "left-aligned",
        "description": "PRD/技术文档：高信息密度",
    },
    "editorial": {
        "keywords": (
            "洞察",
            "分析",
            "观点",
            "行业",
            "长文",
            "白皮书",
            "思考",
            "趋势",
            "深度",
            "insight",
        ),
        "theme": "academic",
        "color_scheme": "warm",
        "cover": True,
        "toc": True,
        "cover_style": "centered",
        "description": "行业洞察/深度长文：衬线典雅",
    },
}

# 场景中文名（供封面 badge 等展示）
SCENE_LABELS: dict[str, str] = {
    "weekly": "周报",
    "quarterly": "季度汇报",
    "business": "商业分析",
    "proposal": "方案提案",
    "portfolio": "作品集",
    "prd": "需求文档",
    "editorial": "行业洞察",
}

# ---------------------------------------------------------------------------
# 风格词别名表（用户自然语言里的风格词 → 主题 / 配色 / 封面 / 目录）
# ---------------------------------------------------------------------------
THEME_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("notion", ("notion", "笔记风", "轻量编辑")),
    ("linear", ("linear", "紧凑", "研发风", "协作风", "开发风")),
    ("apple", ("apple", "苹果", "舒适", "大圆角", "柔和")),
    ("modern", ("现代", "科技", "技术", "程序员", "蓝灰", "极客")),
    ("academic", ("学术", "论文", "典雅", "衬线", "杂志", "文艺", "书卷", "高级感")),
    ("minimal", ("极简", "简洁", "黑白", "克制", "素", "性冷淡")),
    ("universal", ("商务", "正式", "稳重", "通用", "中性", "汇报风", "专业", "高管")),
    ("roadmap", ("路线图", "学习路线", "知识图谱", "技能树", "roadmap")),
]

COLOR_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("blue", ("蓝色", "深蓝", "蓝")),
    ("green", ("绿色", "绿")),
    ("warm", ("暖色", "橙色", "橘", "米色")),
    ("monochrome", ("黑白", "灰度", "灰色")),
    ("purple", ("紫色", "紫")),
]

COVER_STYLE_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("left-aligned", ("左对齐", "左对齐经典", "左侧标题", "left-aligned", "left aligned")),
    ("centered", ("居中", "居中杂志", "居中标题", "centered")),
    ("split", ("左右分屏", "左右分栏", "分屏", "split")),
    ("minimal", ("极简文字", "极简封面", "纯文字封面", "minimal")),
    ("hero-graphic", ("大色块", "图形封面", "hero-graphic", "hero graphic")),
    ("terminal", ("终端", "终端风格", "terminal")),
]

COVER_WORDS: tuple[str, ...] = ("封面", "扉页", "加个封面", "要封面", "带封面")
# 否定词优先于肯定词（"不要封面" 含 "封面"）
NO_COVER_WORDS: tuple[str, ...] = (
    "不要封面",
    "不加封面",
    "无封面",
    "去掉封面",
    "不需要封面",
    "别加封面",
    "不用封面",
)
TOC_WORDS: tuple[str, ...] = ("目录", "加目录", "带目录", "要目录")
NO_TOC_WORDS: tuple[str, ...] = (
    "不要目录",
    "不加目录",
    "无目录",
    "去掉目录",
    "不需要目录",
    "别加目录",
)


def classify_scene(text: str) -> str | None:
    """根据文本关键词匹配场景 ID；命中多个时按优先级取第一个。"""
    lowered = (text or "").lower()
    for scene_id in SCENE_PRIORITY:
        config = SCENES[scene_id]
        if any(kw.lower() in lowered for kw in config["keywords"]):
            return scene_id
    return None


def parse_override(
    text: str,
) -> tuple[str | None, str | None, bool | None, bool | None]:
    """从用户自然语言提取显式风格指定。

    Returns:
        (theme, color_scheme, cover, toc) —— 未指定处为 None
    """
    lowered = (text or "").lower()

    theme: str | None = None
    for candidate, keywords in THEME_ALIASES:
        if any(kw.lower() in lowered for kw in keywords):
            theme = candidate
            break

    color: str | None = None
    for candidate, keywords in COLOR_ALIASES:
        if any(kw.lower() in lowered for kw in keywords):
            color = candidate
            break

    cover: bool | None = None
    if any(w in lowered for w in NO_COVER_WORDS):
        cover = False
    elif any(w in lowered for w in COVER_WORDS):
        cover = True
    toc: bool | None = None
    if any(w in lowered for w in NO_TOC_WORDS):
        toc = False
    elif any(w in lowered for w in TOC_WORDS):
        toc = True

    return theme, color, cover, toc


def parse_cover_style(text: str) -> str | None:
    """从自然语言提取显式封面风格，未指定时返回 None。"""
    lowered = (text or "").lower()
    for style, keywords in COVER_STYLE_ALIASES:
        if any(kw.lower() in lowered for kw in keywords):
            return style
    return None


# ---------------------------------------------------------------------------
# DesignSpec（LLM 设计师）校验：意图阶段 LLM 输出的 design 对象，
# 仅接受合法值；非法字段忽略后走场景/配方默认
# ---------------------------------------------------------------------------

# DesignSpec 的 base_theme 不允许跨到旅行/简历的独立主题体系
_SPEC_THEME_BLOCKLIST = frozenset(
    {"travel", "travel_mag", "travel_swiss", "travel_bento", "travel_aurora", "resume"}
)
_KNOWN_COVER_STYLES = frozenset(style for style, _ in COVER_STYLE_ALIASES)


def _spec_base_theme(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in KNOWN_THEMES and text not in _SPEC_THEME_BLOCKLIST:
        return text
    return None


def _spec_primary_color(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text and resolve_color(text) else None


def _spec_flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _spec_cover_style(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in _KNOWN_COVER_STYLES else None


def _extract_design_spec(
    design_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """提取并校验 DesignSpec 字段，非法值统一为 None。"""
    if not isinstance(design_spec, dict):
        return {}
    return {
        "base_theme": _spec_base_theme(design_spec.get("base_theme")),
        "primary_color": _spec_primary_color(
            design_spec.get("primary_color")
        ),
        "cover": _spec_flag(design_spec.get("cover")),
        "toc": _spec_flag(design_spec.get("toc")),
        "cover_style": _spec_cover_style(design_spec.get("cover_style")),
    }


@dataclass
class DesignDecision:
    """一次设计决策的完整结果（含来源标记，便于日志/调试）。"""

    theme: str
    style: str
    color_scheme: str
    cover: bool
    toc: bool
    scene: str | None = None
    cover_style: str | None = None
    scene_label: str | None = None
    primary_color: str | None = None
    theme_source: str = "recipe"
    color_source: str = "recipe"
    cover_source: str = "recipe"
    toc_source: str = "recipe"
    primary_source: str = "recipe"

    def as_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "color_scheme": self.color_scheme,
            "cover": self.cover,
            "toc": self.toc,
            "scene": self.scene,
            "cover_style": self.cover_style,
            "scene_label": self.scene_label,
            "primary_color": self.primary_color,
            "theme_source": self.theme_source,
            "color_source": self.color_source,
            "cover_source": self.cover_source,
            "toc_source": self.toc_source,
            "primary_source": self.primary_source,
        }


def resolve_design(
    prompt: str,
    *,
    recipe_name: str,
    theme: str | None = None,
    style: str | None = None,
    color_scheme: str | None = None,
    cover: bool | None = None,
    toc: bool | None = None,
    cover_style: str | None = None,
    recipe_theme: str = "universal",
    recipe_color: str = "blue",
    design_spec: dict[str, Any] | None = None,
) -> DesignDecision:
    """按「显式参数 > 风格词 > DesignSpec > 场景分类 > 配方默认」解析设计决策。

    旅行手册（travel）走独立主题体系，场景分类与风格词均不适用，
    仅保留显式 theme/color_scheme（以及 DesignSpec 主色），其余按配方默认。
    """
    spec = _extract_design_spec(design_spec)

    if recipe_name == "travel":
        return DesignDecision(
            theme=theme or recipe_theme,
            style=style or "",
            color_scheme=color_scheme or recipe_color,
            cover=bool(cover) if cover is not None else False,
            toc=bool(toc) if toc is not None else False,
            scene=None,
            primary_color=spec.get("primary_color"),
            theme_source="explicit" if theme else "recipe",
            color_source="explicit" if color_scheme else "recipe",
            cover_source="explicit" if cover is not None else "recipe",
            toc_source="explicit" if toc is not None else "recipe",
            primary_source="design-llm" if spec.get("primary_color") else "recipe",
        )

    text = prompt or ""
    scene = classify_scene(text)
    (
        override_theme,
        override_color,
        override_cover,
        override_toc,
    ) = parse_override(text)
    override_cover_style = parse_cover_style(text)

    # ---- theme ----
    if theme:
        resolved_theme, theme_source = theme, "explicit"
    elif style and style in STYLE_TO_THEME:
        resolved_theme, theme_source = STYLE_TO_THEME[style], "explicit-style"
    elif override_theme:
        resolved_theme, theme_source = override_theme, "override"
    elif spec.get("base_theme"):
        resolved_theme, theme_source = spec["base_theme"], "design-llm"
    elif scene:
        resolved_theme, theme_source = SCENES[scene]["theme"], "scene"
    else:
        resolved_theme, theme_source = recipe_theme, "recipe"

    # ---- color_scheme（DesignSpec 提供主色时记录到 primary_color，渲染层派生）----
    resolved_color, color_source = recipe_color, "recipe"
    primary_color, primary_source = None, "recipe"
    if color_scheme:
        resolved_color, color_source = color_scheme, "explicit"
    elif override_color:
        resolved_color, color_source = override_color, "override"
    elif spec.get("primary_color"):
        primary_color, primary_source = spec["primary_color"], "design-llm"
        resolved_color, color_source = recipe_color, "recipe"
    elif scene:
        resolved_color, color_source = SCENES[scene]["color_scheme"], "scene"

    # ---- cover / toc ----
    if cover is not None:
        resolved_cover, cover_source = cover, "explicit"
    elif override_cover is not None:
        resolved_cover, cover_source = override_cover, "override"
    elif spec.get("cover") is not None:
        resolved_cover, cover_source = spec["cover"], "design-llm"
    elif scene:
        resolved_cover, cover_source = SCENES[scene]["cover"], "scene"
    else:
        resolved_cover, cover_source = True, "recipe"

    if toc is not None:
        resolved_toc, toc_source = toc, "explicit"
    elif override_toc is not None:
        resolved_toc, toc_source = override_toc, "override"
    elif spec.get("toc") is not None:
        resolved_toc, toc_source = spec["toc"], "design-llm"
    elif scene:
        resolved_toc, toc_source = SCENES[scene]["toc"], "scene"
    else:
        resolved_toc, toc_source = False, "recipe"

    return DesignDecision(
        theme=resolved_theme,
        style=style or "",
        color_scheme=resolved_color,
        cover=resolved_cover,
        toc=resolved_toc,
        scene=scene,
        cover_style=(
            cover_style
            or override_cover_style
            or spec.get("cover_style")
            or (SCENES[scene]["cover_style"] if scene else "left-aligned")
        ),
        scene_label=SCENE_LABELS.get(scene) if scene else None,
        primary_color=primary_color,
        theme_source=theme_source,
        color_source=color_source,
        cover_source=cover_source,
        toc_source=toc_source,
        primary_source=primary_source,
    )
