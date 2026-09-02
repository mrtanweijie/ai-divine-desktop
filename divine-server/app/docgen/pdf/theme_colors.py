"""主题颜色体系：预设色表、颜色名映射、HSL 派生与旅行/通用主题覆盖计算。

从 theme_manager.py（原 2,039 行单文件）拆出，无内部依赖。
"""

from __future__ import annotations

import colorsys
import re

# 语义色 token（P0-1）：浅色/深色主题两套，模块 callout-box / stat-trend 等引用
_SEMANTIC_LIGHT = {
    "--success": "#16A34A",
    "--success-bg": "#F0FDF4",
    "--success-soft": "#BBF7D0",
    "--warning": "#D97706",
    "--warning-bg": "#FFFBEB",
    "--error": "#DC2626",
    "--error-bg": "#FEF2F2",
    "--error-soft": "#FECACA",
}


_SEMANTIC_DARK = {
    "--success": "#4ADE80",
    "--success-bg": "#052E16",
    "--success-soft": "#86EFAC",
    "--warning": "#FBBF24",
    "--warning-bg": "#451A03",
    "--error": "#F87171",
    "--error-bg": "#450A0A",
    "--error-soft": "#FCA5A5",
}


_DARK_THEMES = frozenset({"bold", "terminal"})


def _semantic_colors(theme_id: str) -> dict[str, str]:
    """按主题明暗返回语义色变量表（浅色主题深色语义，深色主题反转为亮色）。"""
    return dict(_SEMANTIC_DARK if theme_id in _DARK_THEMES else _SEMANTIC_LIGHT)


TRAVEL_COLOR_PRESETS: dict[str, dict[str, str]] = {
    "teal": {
        "--color-primary": "#2a5a5b",
        "--color-accent": "#3a8a8b",
        "--color-accent-light": "#5ba3a4",
        "--bg-highlight": "#f5f1e8",
        "--bg-cover": "#2a3e3e",
    },
    "warm": {
        "--color-primary": "#b8743a",
        "--color-accent": "#d49556",
        "--color-accent-light": "#e5b37c",
        "--bg-highlight": "#fff3e6",
        "--bg-cover": "#5c3a24",
    },
    "blue": {
        "--color-primary": "#2f5b9e",
        "--color-accent": "#3d7bd6",
        "--color-accent-light": "#6fa8e8",
        "--bg-highlight": "#edf4fc",
        "--bg-cover": "#263a5c",
    },
    "green": {
        "--color-primary": "#2e6b4f",
        "--color-accent": "#3e9a6f",
        "--color-accent-light": "#72bd98",
        "--bg-highlight": "#edf7f1",
        "--bg-cover": "#243f35",
    },
    "purple": {
        "--color-primary": "#5b4b8a",
        "--color-accent": "#7a6bc2",
        "--color-accent-light": "#a99ce0",
        "--bg-highlight": "#f2effa",
        "--bg-cover": "#332b4a",
    },
    "monochrome": {
        "--color-primary": "#333333",
        "--color-accent": "#666666",
        "--color-accent-light": "#999999",
        "--bg-highlight": "#f5f5f5",
        "--bg-cover": "#222222",
    },
}


# travel_mag（杂志版）完整主题色预设。
# 每套主题定义 --teal-* 阶梯（主色）、--amber-*（点缀色）与 hero 封面渐变，
# 换主题色时整体覆盖。新增主题只需在此表加一项即可（键名为 color_scheme 取值）。
TRAVEL_MAG_THEMES: dict[str, dict[str, str]] = {
    # 深青绿（默认）：青绿 + 琥珀暖，经典雅致（模板 :root 默认值）
    "teal": {
        "--teal-50": "#EFF6F6", "--teal-100": "#DCECEC",
        "--teal-200": "#B8D9D9", "--teal-300": "#8CC0C1",
        "--teal-400": "#5BA3A4", "--teal-500": "#3A8A8B",
        "--teal-600": "#2A5A5B", "--teal-700": "#23494A",
        "--teal-800": "#1C3A3B", "--teal-900": "#162E2F",
        "--amber-100": "#F7EAD8", "--amber-300": "#E0BC8C",
        "--amber-500": "#C08552", "--amber-700": "#9A6536",
        "--bg-highlight": "#F6F2E9", "--bg-cover": "#162E2F",
        "--bg-soft": "#F4F7F7", "--border-light": "#E3E9E8",
        "--border-table": "#D8E2E1", "--text-primary": "#22302F",
        "--text-secondary": "#556563", "--text-muted": "#8A9A97",
        "--hero-1": "#162E2F", "--hero-2": "#23494A",
        "--hero-3": "#2A5A5B", "--hero-4": "#3A8A8B",
        "--hero-glow-1": "rgba(192,133,82,0.45)",
        "--hero-glow-2": "rgba(91,163,164,0.35)",
    },
    # 冰蓝主题（提取自 travel-guide-optimized.html）：冰川/极光质感
    "iceblue": {
        "--teal-50": "#EDF3F8", "--teal-100": "#D2E2EE",
        "--teal-200": "#A8C8DE", "--teal-300": "#7EAEC9",
        "--teal-400": "#5B98BD", "--teal-500": "#3A6B8C",
        "--teal-600": "#2C5775", "--teal-700": "#1E4361",
        "--teal-800": "#16344A", "--teal-900": "#0F2638",
        "--amber-100": "#E0EBF2", "--amber-300": "#A8C4D8",
        "--amber-500": "#6B9BBA", "--amber-700": "#3D6B8A",
        "--bg-highlight": "#EDF3F8", "--bg-cover": "#0F2638",
        "--bg-soft": "#EFF4F8", "--border-light": "#D8E0E8",
        "--border-table": "#C8D4E0", "--text-primary": "#1A2433",
        "--text-secondary": "#4A5A6E", "--text-muted": "#8A9BA8",
        "--hero-1": "#0F2638", "--hero-2": "#1E4361",
        "--hero-3": "#2C5775", "--hero-4": "#3A6B8C",
        "--hero-glow-1": "rgba(107,155,186,0.55)",
        "--hero-glow-2": "rgba(126,174,201,0.5)",
    },
    # 沙漠落日（提取自 travel-guide-optimized.html）：暖沙 + 落日金，辽阔热烈
    "desert": {
        "--teal-50": "#FBF3E4", "--teal-100": "#F5E6C8",
        "--teal-200": "#EBCF98", "--teal-300": "#DDB56A",
        "--teal-400": "#C89442", "--teal-500": "#A66A2E",
        "--teal-600": "#8B4513", "--teal-700": "#6D350F",
        "--teal-800": "#5C3A1E", "--teal-900": "#3D2510",
        "--amber-100": "#FBEDD8", "--amber-300": "#F0C97A",
        "--amber-500": "#D49142", "--amber-700": "#8B5A1E",
        "--bg-highlight": "#FBF3E4", "--bg-cover": "#3D2510",
        "--bg-soft": "#FAF5EE", "--border-light": "#EDE0CD",
        "--border-table": "#E0D0B8", "--text-primary": "#2A1F12",
        "--text-secondary": "#5C4A2E", "--text-muted": "#9A8A6E",
        "--hero-1": "#3D2510", "--hero-2": "#5C3A1E",
        "--hero-3": "#8B4513", "--hero-4": "#C77D3C",
        "--hero-glow-1": "rgba(192,133,82,0.55)",
        "--hero-glow-2": "rgba(212,145,66,0.4)",
    },
    # 复古胶片（提取自 travel-guide-optimized.html）：暖灰 + 古铜棕，怀旧胶片
    "vintage": {
        "--teal-50": "#F1EFE8", "--teal-100": "#E5E2D8",
        "--teal-200": "#D3D1C7", "--teal-300": "#B4B2A9",
        "--teal-400": "#888780", "--teal-500": "#6B6A5E",
        "--teal-600": "#5F5E5A", "--teal-700": "#4A4945",
        "--teal-800": "#444441", "--teal-900": "#2C2C2A",
        "--amber-100": "#F7EAD8", "--amber-300": "#D4A868",
        "--amber-500": "#A6772E", "--amber-700": "#633806",
        "--bg-highlight": "#F1EFE8", "--bg-cover": "#2C2C2A",
        "--bg-soft": "#F5F4EF", "--border-light": "#DDD9CC",
        "--border-table": "#CDC8B8", "--text-primary": "#2C2A24",
        "--text-secondary": "#5A5648", "--text-muted": "#8E8A78",
        "--hero-1": "#2C2C2A", "--hero-2": "#444441",
        "--hero-3": "#5F5E5A", "--hero-4": "#888780",
        "--hero-glow-1": "rgba(166,119,46,0.4)",
        "--hero-glow-2": "rgba(136,135,128,0.35)",
    },
    # 午夜墨黑（提取自 travel-guide-optimized.html）：墨蓝 + 夜紫，深邃静谧
    "midnight": {
        "--teal-50": "#2C2C40", "--teal-100": "#262638",
        "--teal-200": "#202032", "--teal-300": "#1A1A2A",
        "--teal-400": "#5A5A7E", "--teal-500": "#4A4A6E",
        "--teal-600": "#3A3A5C", "--teal-700": "#2E2E48",
        "--teal-800": "#222238", "--teal-900": "#16161E",
        "--amber-100": "#E8E6F0", "--amber-300": "#B0ACCC",
        "--amber-500": "#807CA8", "--amber-700": "#504C78",
        "--bg-page": "#FFFFFF", "--bg-highlight": "#F0F0F5",
        "--bg-cover": "#1A1A2E", "--bg-soft": "#F5F5F8",
        "--border-light": "#E0E0E8", "--border-table": "#D0D0DC",
        "--text-primary": "#1A1A2E", "--text-secondary": "#3A3A5C",
        "--text-muted": "#6A6A8A", "--text-inverse": "#FFFFFF",
        "--hero-1": "#0E0E18", "--hero-2": "#1A1A2E",
        "--hero-3": "#2E2E48", "--hero-4": "#3A3A5C",
        "--hero-glow-1": "rgba(90,90,126,0.4)",
        "--hero-glow-2": "rgba(128,124,168,0.3)",
    },

    # 纯黑主题（提取自 travel-guide-optimized.html）：极简纯黑
    "pureblack": {
        # 纯黑主题：teal 阶梯改为正常浅→深灰阶（浅色档做背景如 .ic/todo-list，
        # 深色档做文字如 teal-700），避免黑底黑字；hero/cover 保持深色。
        "--teal-50": "#F7F7F7", "--teal-100": "#EBEBEB",
        "--teal-200": "#DCDCDC", "--teal-300": "#C9C9C9",
        "--teal-400": "#9E9E9E", "--teal-500": "#757575",
        "--teal-600": "#333333", "--teal-700": "#1A1A1A",
        "--teal-800": "#111111", "--teal-900": "#000000",
        "--amber-100": "#E0E0E0", "--amber-300": "#A0A0A0",
        "--amber-500": "#707070", "--amber-700": "#404040",
        "--bg-page": "#FFFFFF", "--bg-highlight": "#F5F5F5",
        "--bg-cover": "#000000", "--bg-soft": "#FAFAFA",
        "--border-light": "#E0E0E0", "--border-table": "#CCCCCC",
        "--text-primary": "#000000", "--text-secondary": "#333333",
        "--text-muted": "#666666", "--text-inverse": "#FFFFFF",
        "--hero-1": "#000000", "--hero-2": "#1A1A1A",
        "--hero-3": "#333333", "--hero-4": "#555555",
        "--hero-glow-1": "rgba(60,60,60,0.2)",
        "--hero-glow-2": "rgba(30,30,30,0.15)",
    },
    # 雾凇青（提取自 travel-guide-optimized.html）：雾灰青 + 灰白，清冷淡雅
    "mistsage": {
        "--teal-50": "#F0F5F4", "--teal-100": "#E0EBE9",
        "--teal-200": "#C8DDD9", "--teal-300": "#A8C5C0",
        "--teal-400": "#8AB5B0", "--teal-500": "#6BA098",
        "--teal-600": "#5A8A82", "--teal-700": "#4A756E",
        "--teal-800": "#3A5A56", "--teal-900": "#2A4540",
        "--amber-100": "#E8EFEE", "--amber-300": "#B8C8C5",
        "--amber-500": "#8AA8A4", "--amber-700": "#5A7A76",
        "--bg-highlight": "#E8EFEE", "--bg-cover": "#2A4540",
        "--bg-soft": "#F2F6F5", "--border-light": "#DDE5E3",
        "--border-table": "#CCD8D5", "--text-primary": "#2A4540",
        "--text-secondary": "#4A6A64", "--text-muted": "#7A9A94",
        "--hero-1": "#2A4540", "--hero-2": "#3A5A56",
        "--hero-3": "#5A8A82", "--hero-4": "#8AB5B0",
        "--hero-glow-1": "rgba(138,181,176,0.35)",
        "--hero-glow-2": "rgba(106,160,152,0.3)",
    },
    # 晨雾灰蓝（提取自 travel-guide-optimized.html）：灰蓝 + 浅雾蓝，宁静柔和
    "mistblue": {
        "--teal-50": "#F0F4F8", "--teal-100": "#E0EAF0",
        "--teal-200": "#C8D8E4", "--teal-300": "#A8BDD0",
        "--teal-400": "#8AA8C0", "--teal-500": "#6A8AAA",
        "--teal-600": "#587892", "--teal-700": "#48687C",
        "--teal-800": "#3A5870", "--teal-900": "#2A4858",
        "--amber-100": "#EBF0F5", "--amber-300": "#BCCBD8",
        "--amber-500": "#8AA0B0", "--amber-700": "#5A7080",
        "--bg-highlight": "#EBF0F5", "--bg-cover": "#2A4858",
        "--bg-soft": "#F2F5F8", "--border-light": "#DDE4EA",
        "--border-table": "#CCD6E0", "--text-primary": "#2A4858",
        "--text-secondary": "#4A687C", "--text-muted": "#7A92A4",
        "--hero-1": "#2A4858", "--hero-2": "#3A5870",
        "--hero-3": "#587892", "--hero-4": "#8AA8C0",
        "--hero-glow-1": "rgba(138,168,192,0.35)",
        "--hero-glow-2": "rgba(106,138,170,0.3)",
    },
    # 暮山紫（提取自 travel-guide-optimized.html）：灰紫 + 淡藕色，温柔雅致
    "duskmauve": {
        "--teal-50": "#F2EFF4", "--teal-100": "#E4DFEA",
        "--teal-200": "#CCC4D6", "--teal-300": "#B8A8C0",
        "--teal-400": "#9A8AAB", "--teal-500": "#7E6E90",
        "--teal-600": "#6A5C7C", "--teal-700": "#584C6A",
        "--teal-800": "#4A3A5C", "--teal-900": "#382A48",
        "--amber-100": "#F0EDF2", "--amber-300": "#C8BECF",
        "--amber-500": "#9A8AAB", "--amber-700": "#6A5C7C",
        "--bg-highlight": "#F0EDF2", "--bg-cover": "#382A48",
        "--bg-soft": "#F4F2F6", "--border-light": "#E0DCE6",
        "--border-table": "#D0CAD8", "--text-primary": "#382A48",
        "--text-secondary": "#5A4C6A", "--text-muted": "#8A7A9A",
        "--hero-1": "#382A48", "--hero-2": "#4A3A5C",
        "--hero-3": "#6A5C7C", "--hero-4": "#9A8AAB",
        "--hero-glow-1": "rgba(154,138,171,0.35)",
        "--hero-glow-2": "rgba(126,110,144,0.3)",
    },
    # 初秋藕粉（提取自 travel-guide-optimized.html）：藕粉 + 暖灰，温暖不甜腻
    "lotuspink": {
        "--teal-50": "#F5F0EF", "--teal-100": "#EBE0DE",
        "--teal-200": "#DAC8C5", "--teal-300": "#D8B8B0",
        "--teal-400": "#C4A098", "--teal-500": "#A88880",
        "--teal-600": "#8E7068", "--teal-700": "#745852",
        "--teal-800": "#6A4A42", "--teal-900": "#4A342E",
        "--amber-100": "#F5EFEF", "--amber-300": "#D8C0BC",
        "--amber-500": "#B89890", "--amber-700": "#8A6A62",
        "--bg-highlight": "#F5EFEF", "--bg-cover": "#4A342E",
        "--bg-soft": "#F6F2F1", "--border-light": "#E5D8D5",
        "--border-table": "#D6C5C0", "--text-primary": "#4A342E",
        "--text-secondary": "#6A4A42", "--text-muted": "#9A7A72",
        "--hero-1": "#4A342E", "--hero-2": "#6A4A42",
        "--hero-3": "#8E7068", "--hero-4": "#C4A098",
        "--hero-glow-1": "rgba(196,160,152,0.35)",
        "--hero-glow-2": "rgba(168,136,128,0.3)",
    },
    # 沙丘米（提取自 travel-guide-optimized.html）：暖米沙 + 浅卡其，自然质朴
    "dunesand": {
        "--teal-50": "#F5F2EB", "--teal-100": "#EBE6D8",
        "--teal-200": "#DCD4BE", "--teal-300": "#D4C8B0",
        "--teal-400": "#BCAE92", "--teal-500": "#A49678",
        "--teal-600": "#8C7E62", "--teal-700": "#746450",
        "--teal-800": "#5C5240", "--teal-900": "#403828",
        "--amber-100": "#F5F2EB", "--amber-300": "#D8CEB8",
        "--amber-500": "#B8A882", "--amber-700": "#82745A",
        "--bg-highlight": "#F5F2EB", "--bg-cover": "#403828",
        "--bg-soft": "#F6F4EE", "--border-light": "#E2DCCF",
        "--border-table": "#D2C8B8", "--text-primary": "#403828",
        "--text-secondary": "#5C5240", "--text-muted": "#8A7E62",
        "--hero-1": "#403828", "--hero-2": "#5C5240",
        "--hero-3": "#8C7E62", "--hero-4": "#BCAE92",
        "--hero-glow-1": "rgba(188,174,146,0.35)",
        "--hero-glow-2": "rgba(164,150,120,0.3)",
    },
    # 烟雨灰（提取自 travel-guide-optimized.html）：暖灰 + 银灰，极简克制
    "smokegray": {
        "--teal-50": "#F2F1EE", "--teal-100": "#E6E4E0",
        "--teal-200": "#D2D0CC", "--teal-300": "#C0BFB8",
        "--teal-400": "#A8A7A0", "--teal-500": "#8E8D86",
        "--teal-600": "#76756E", "--teal-700": "#5E5D56",
        "--teal-800": "#4A4945", "--teal-900": "#343430",
        "--amber-100": "#F2F1EE", "--amber-300": "#C8C6C0",
        "--amber-500": "#A8A7A0", "--amber-700": "#76756E",
        "--bg-highlight": "#F2F1EE", "--bg-cover": "#343430",
        "--bg-soft": "#F4F3F0", "--border-light": "#DDD9D4",
        "--border-table": "#CCC8C2", "--text-primary": "#343430",
        "--text-secondary": "#4A4945", "--text-muted": "#7A7972",
        "--hero-1": "#343430", "--hero-2": "#4A4945",
        "--hero-3": "#76756E", "--hero-4": "#A8A7A0",
        "--hero-glow-1": "rgba(168,167,160,0.35)",
        "--hero-glow-2": "rgba(142,141,134,0.3)",
    },
}


# 常用颜色名 → 基准色值（未收录的颜色名可走 derive_travel_palette 的 HSL 派生）
COLOR_NAMES: dict[str, str] = {    "red": "#E74C3C",
    "红色": "#E74C3C",
    "orange": "#E67E22",
    "橙色": "#E67E22",
    "yellow": "#D4A017",
    "黄色": "#D4A017",
    "green": "#27AE60",
    "绿色": "#27AE60",
    "cyan": "#1FA8A0",
    "青色": "#1FA8A0",
    "blue": "#2F5B9E",
    "蓝色": "#2F5B9E",
    "purple": "#5B4B8A",
    "紫色": "#5B4B8A",
    "pink": "#C94F7C",
    "粉色": "#C94F7C",
    "brown": "#8B5E3C",
    "棕色": "#8B5E3C",
    "teal": "#2A5A5B",
    "青绿": "#2A5A5B",
    "gray": "#555555",
    "灰色": "#555555",
    "black": "#222222",
    "黑色": "#222222",
    "navy": "#1F3A5F",
    "藏青": "#1F3A5F",
    "酒红": "#7B2D3B",
    "墨绿": "#1F4A38",
    "森绿": "#2E6B4F",
    "天蓝": "#3B82C4",
    "靛蓝": "#3F51B5",
    "琥珀": "#B8743A",
    "金黄": "#D4A017",
    "珊瑚": "#E87A5D",
    "石板灰": "#4A5568",
}


# 扩展配色方案（iceblue 等 12 个旅行杂志预设）在通用主题下的主色基准，
# 取值与 TRAVEL_MAG_THEMES 各预设的 --teal-600 一致，保证两个体系观感统一。
SCHEME_PRIMARY_COLORS: dict[str, str] = {
    "iceblue": "#2C5775",
    "desert": "#8B4513",
    "vintage": "#5F5E5A",
    "midnight": "#3A3A5C",
    "pureblack": "#333333",
    "mistsage": "#5A8A82",
    "mistblue": "#587892",
    "duskmauve": "#6A5C7C",
    "lotuspink": "#8E7068",
    "dunesand": "#8C7E62",
    "smokegray": "#76756E",
}


_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


_RGB_COLOR_RE = re.compile(
    r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$",
    re.IGNORECASE,
)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    match = _HEX_COLOR_RE.match((value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def _shift_lightness(
    rgb: tuple[int, int, int], delta: float
) -> tuple[int, int, int]:
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    lightness = max(0.0, min(1.0, lightness + delta))
    r2, g2, b2 = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _resolve_color(value: str) -> tuple[int, int, int] | None:
    """把 #hex / rgb() / 颜色名 统一解析为 RGB；无法解析返回 None。"""
    text = (value or "").strip()
    rgb = _hex_to_rgb(text)
    if rgb:
        return rgb
    match = _RGB_COLOR_RE.match(text)
    if match:
        r, g, b = (int(part) for part in match.groups())
        if all(0 <= channel <= 255 for channel in (r, g, b)):
            return (r, g, b)
    named = COLOR_NAMES.get(text.lower())
    if named:
        return _hex_to_rgb(named)
    return None


# 公开别名：设计决策层校验主色是否可解析（不依赖私有函数名）
resolve_color = _resolve_color


def derive_travel_palette(primary_color: str) -> dict[str, str] | None:
    """从单一主色派生整套旅行手册色调；无法解析时返回 None。

    派生规则（与预设 teal 的视觉关系一致）：
    - --color-primary：主色压深到 ≤35% 亮度（保证表头/封面条带白字可读）；
    - --color-accent / --color-accent-light：主色逐级提亮；
    - --bg-highlight：主色极浅的米色系背景块；
    - --bg-cover：主色加深的封面深色条带。
    """
    rgb = _resolve_color(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    primary_l = min(lightness, 0.35)
    primary = colorsys.hls_to_rgb(hue, primary_l, saturation)
    primary_rgb = (
        round(primary[0] * 255),
        round(primary[1] * 255),
        round(primary[2] * 255),
    )
    return {
        "--color-primary": _rgb_to_hex(primary_rgb),
        "--color-accent": _rgb_to_hex(_shift_lightness(primary_rgb, 0.10)),
        "--color-accent-light": _rgb_to_hex(
            _shift_lightness(primary_rgb, 0.22)
        ),
        "--bg-highlight": _rgb_to_hex(_shift_lightness(primary_rgb, 0.42)),
        "--bg-cover": _rgb_to_hex(_shift_lightness(primary_rgb, -0.12)),
    }


def derive_universal_palette(primary_color: str) -> dict[str, str] | None:
    """从单一主色派生通用主题（非 travel）的 CSS 变量覆盖。

    派生关系与 classic COLOR_MAP（blue: #2563eb / #eaf1fe / #1e40af）一致：
    - --primary / --accent：主色压到可读亮度（保证表头白字、封面条带可读）；
    - --primary-light：同色相极浅底色（引用、标签、callout 背景）；
    - --primary-dark：主色加深（深色强调文本）。
    无法解析时返回 None。
    """
    rgb = _resolve_color(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    primary_l = min(max(lightness, 0.18), 0.48)
    primary_rgb = (
        round(channel * 255)
        for channel in colorsys.hls_to_rgb(hue, primary_l, saturation)
    )
    primary_hex = _rgb_to_hex(primary_rgb)
    light_rgb = colorsys.hls_to_rgb(
        hue, 0.95, min(max(saturation, 0.20), 0.85)
    )
    dark_rgb = colorsys.hls_to_rgb(
        hue, max(primary_l - 0.14, 0.12), saturation
    )
    return {
        "--primary": primary_hex,
        "--accent": primary_hex,
        "--primary-light": _rgb_to_hex(
            round(channel * 255) for channel in light_rgb
        ),
        "--primary-dark": _rgb_to_hex(
            round(channel * 255) for channel in dark_rgb
        ),
    }


# theme_colors 里旅行风格的变量名 → 通用主题变量名的等价映射
#（无对应语义的键保持原名透传，注入 :root 后不影响渲染）
_UNIVERSAL_COLOR_KEY_ALIASES: dict[str, str] = {
    "--color-primary": "--primary",
    "--color-primary-dark": "--primary-dark",
    "--color-accent": "--accent",
    "--text-primary": "--text",
    "--bg-highlight": "--bg-soft",
}


def universal_color_overrides(
    custom: dict[str, str] | None,
) -> dict[str, str]:
    """把 theme_colors 归一化为通用主题的 CSS 变量覆盖。

    与 travel_color_overrides 的约定一致：只传 {"--color-primary": "<颜色>"}
    时自动派生整套配套色；显式给出的其他变量优先级最高（覆盖派生值）。
    """
    if not custom:
        return {}
    normalized: dict[str, str] = {}
    for key, value in custom.items():
        clean_key = str(key).strip().lower()
        mapped = _UNIVERSAL_COLOR_KEY_ALIASES.get(clean_key, clean_key)
        normalized[mapped] = str(value)
    merged: dict[str, str] = {}
    primary = normalized.get("--primary")
    if primary and "--primary-light" not in normalized:
        derived = derive_universal_palette(primary)
        if derived:
            merged.update(derived)
    merged.update(normalized)
    return merged


def _derive_hero_vars(scale: dict[str, str]) -> dict[str, str]:
    """从派生出的 teal 阶梯生成 hero 封面渐变变量（cover-hero 跟随主题色）。

    与 TRAVEL_MAG_THEMES 预设中 hero 的取色规则一致：
    hero-1 ← teal-900（最深）、hero-2 ← teal-700、hero-3 ← teal-600（主色）、
    hero-4 ← teal-400（亮色），光晕取对应色号的半透明。
    """
    def _rgba(hex_value: str | None, alpha: float) -> str | None:
        rgb = _hex_to_rgb(hex_value or "")
        if not rgb:
            return None
        return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"

    hero = {
        "--hero-1": scale.get("--teal-900") or scale.get("--teal-800") or "#162E2F",
        "--hero-2": scale.get("--teal-700") or scale.get("--teal-600") or "#23494A",
        "--hero-3": scale.get("--teal-600") or "#2A5A5B",
        "--hero-4": scale.get("--teal-400") or scale.get("--teal-500") or "#3A8A8B",
    }
    glow1 = _rgba(scale.get("--teal-500"), 0.45)
    glow2 = _rgba(scale.get("--teal-300"), 0.35)
    if glow1:
        hero["--hero-glow-1"] = glow1
    if glow2:
        hero["--hero-glow-2"] = glow2
    return hero


def _derive_amber_vars(scale: dict[str, str]) -> dict[str, str]:
    """从派生的 teal 阶梯生成 amber 点缀色变量。

    模板多处使用 --amber-*（photo-placeholder 渐变、标签、高亮块等），
    派生路径（自定义色/旧预设名）不命中 TRAVEL_MAG_THEMES 精确分支，
    若不生成会残留模板默认琥珀色。这里直接复用 teal 阶梯同色系值，
    保证整本手册随主题色一致（淡雅系列预设的 amber 本就与 teal 同色相）。
    """
    amber: dict[str, str] = {}
    for src, dst in [
        ("--teal-100", "--amber-100"),
        ("--teal-300", "--amber-300"),
        ("--teal-500", "--amber-500"),
        ("--teal-700", "--amber-700"),
    ]:
        if scale.get(src):
            amber[dst] = scale[src]
    return amber


def derive_teal_scale(primary_color: str) -> dict[str, str] | None:
    """从单一主色派生 travel_mag（杂志版）使用的 teal 阶梯变量。

    原模板 --teal-50..900 以 #2A5A5B 为基准：越浅越接近白、越深越接近黑。
    这里以主色为 600 档，按同比例向浅色（50-500）和深色（700-900）扩展。
    """
    rgb = _resolve_color(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    # 600 档亮度 = min(主色亮度, 0.30)（深青绿基准 #2A5A5B 亮度≈0.27）
    base_l = min(lightness, 0.30)
    scale = {
        "--teal-600": _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, base_l, saturation))
        ),
    }
    # 浅色档：50→500 逐步接近白（亮度递增）
    for idx, lightness in enumerate(
        [min(base_l + 0.62, 0.97), min(base_l + 0.50, 0.93),
         min(base_l + 0.38, 0.87), min(base_l + 0.27, 0.80),
         min(base_l + 0.15, 0.72), base_l + 0.05]
    ):
        key = "--teal-50" if idx == 0 else f"--teal-{idx * 100}"
        scale[key] = _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, lightness, saturation))
        )
    # 深色档：700→900 逐步接近黑
    for idx, lightness in enumerate(
        [max(base_l - 0.06, 0.06), max(base_l - 0.12, 0.04),
         max(base_l - 0.18, 0.02)]
    ):
        key = f"--teal-{700 + idx * 100}"
        scale[key] = _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, lightness, saturation))
        )
    return scale


def _resolve_theme_key(value: str) -> str | None:
    """把 LLM 可能传的主题名解析为 TRAVEL_MAG_THEMES 的 key。

    支持形式：中文 label（雾凇青）、key 带括号（mistsage（雾凇青）/
    雾凇青（mistsage））、key 前后有多余空白；无法识别返回 None。
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in TRAVEL_MAG_THEMES:
        return text
    # 中文 label → key（如 雾凇青 → mistsage）
    for theme_key, theme_vars in TRAVEL_MAG_THEMES.items():
        label = _TRAVEL_MAG_LABELS.get(theme_key)
        if label and label.lower() in text:
            return theme_key
    # 形如 "mistsage（雾凇青）" 或 "雾凇青（mistsage）"：提取括号内/外的英文 key
    for token in re.split(r"[()（）\s,，;；]+", text):
        if token and token in TRAVEL_MAG_THEMES:
            return token
    return None


_TRAVEL_MAG_LABELS: dict[str, str] = {
    "teal": "深青绿",
    "iceblue": "极地冰蓝",
    "desert": "沙漠落日",
    "vintage": "复古胶片",
    "midnight": "午夜墨黑",
    "pureblack": "纯黑",
    "mistsage": "雾凇青",
    "mistblue": "晨雾灰蓝",
    "duskmauve": "暮山紫",
    "lotuspink": "初秋藕粉",
    "dunesand": "沙丘米",
    "smokegray": "烟雨灰",
}


def _ensure_dark_cover(overrides: dict[str, str]) -> None:
    """--bg-cover 是封面深色条带（cover-band 背景，其上为白字），
    LLM 有时会传浅色（如 #F2E9DC/#E9F2F7）导致白字看不清：
    亮度超过阈值时压深为派生阶梯最深色（teal-900）。"""
    cover = overrides.get("--bg-cover")
    if not cover:
        return
    rgb = _hex_to_rgb(str(cover).strip().lstrip("#"))
    if not rgb:
        return
    luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    if luminance > 150:
        scale = derive_teal_scale(
            overrides.get("--color-primary") or str(cover)
        )
        deep = (
            (scale or {}).get("--teal-900")
            or overrides.get("--teal-900")
            or "#2C2C2A"
        )
        overrides["--bg-cover"] = deep


def travel_color_overrides(
    color_scheme: str = "teal",
    custom: dict[str, str] | None = None,
    theme: str = "travel",
) -> dict[str, str]:
    """计算旅行手册的 CSS 变量覆盖。

    color_scheme 支持预设名（teal/blue/green/warm/purple/monochrome），
    也支持直接传颜色名或色值（如 "红色"、"#E74C3C"）自动派生整套色调；
    custom 里只需给 {"--color-primary": "<颜色>"} 即可派生配套色，
    显式传入的其他变量（--color-accent/--bg-cover/--bg-highlight 等）优先级最高。
    theme=travel_mag 时额外派生 --teal-50..900 阶梯变量。
    """
    key = (color_scheme or "teal").strip().lower()
    # 兼容 LLM 传中文主题名（"雾凇青"）或混合写法（"雾凇青（mistsage）"）：
    # 把中文 label 映射回主题 key，避免 fallback 成默认 teal。
    if key not in TRAVEL_MAG_THEMES and key not in TRAVEL_COLOR_PRESETS:
        resolved = _resolve_theme_key(key)
        if resolved:
            key = resolved
    # travel_mag 且命中完整主题预设：直接用整套主题色（精确颜色，不做 HSL 派生）
    if theme == "travel_mag" and key in TRAVEL_MAG_THEMES:
        overrides = dict(TRAVEL_MAG_THEMES[key])
        # 仍保留经典变量映射，供封面/通用样式使用
        preset = TRAVEL_COLOR_PRESETS.get(key)
        if preset:
            overrides.update(preset)
        primary = custom.get("--color-primary") if custom else None
        if primary:
            # 用户自定义主色（如通过“其他”输入）：
            # 从主色派生整套 teal 阶梯 + hero 封面渐变 + amber 点缀 + cover 深色，
            # 覆盖预设主题色，避免只改 --color-primary 一个变量（mag 模板不用它）。
            scale = derive_teal_scale(str(primary))
            if scale:
                overrides.update(scale)
                overrides.update(_derive_hero_vars(scale))
                overrides.update(_derive_amber_vars(scale))
                # cover-band 背景：取派生阶梯最深色（teal-900），与预设主题一致。
                # 直接覆盖（custom 显式给的 --bg-cover 会在 update(custom) 时覆盖回来）
                overrides["--bg-cover"] = (
                    scale.get("--teal-900") or scale.get("--teal-800")
                )
            overrides["--color-primary"] = str(primary)
        overrides.update(custom or {})
        overrides.pop("--primary", None)
        _ensure_dark_cover(overrides)
        return overrides
    if key in TRAVEL_COLOR_PRESETS:
        overrides = dict(TRAVEL_COLOR_PRESETS[key])
        primary_source = overrides.get("--color-primary")
    elif key in TRAVEL_MAG_THEMES:
        # 经典模板（travel）没有 --teal-* 阶梯变量：把 mag 主题映射为经典变量，
        # 使淡雅系列（雾凇青/晨雾灰蓝/沙丘米等）在经典模板下也能正确换色。
        mag = TRAVEL_MAG_THEMES[key]
        overrides = {
            "--color-primary": mag["--teal-600"],
            "--color-primary-dark": mag["--teal-800"],
            "--color-accent": mag["--teal-500"],
            "--color-accent-light": mag["--teal-400"],
            "--bg-highlight": mag["--bg-highlight"],
            "--bg-cover": mag["--bg-cover"],
        }
        primary_source = overrides.get("--color-primary")
    else:
        derived = derive_travel_palette(key)
        overrides = (
            derived if derived else dict(TRAVEL_COLOR_PRESETS["teal"])
        )
        primary_source = overrides.get("--color-primary")
    custom = dict(custom or {})
    primary = custom.get("--color-primary")
    if primary:
        derived = derive_travel_palette(str(primary))
        if derived:
            overrides.update(derived)
        primary_source = str(primary)
    if theme == "travel_mag" and primary_source:
        scale = derive_teal_scale(primary_source)
        if scale:
            overrides.update(scale)
            # 派生 hero 封面渐变变量，使 cover-hero 跟随主题色
            # （LLM 传旧预设名/自定义色值时不会命中 TRAVEL_MAG_THEMES 精确分支）
            overrides.update(_derive_hero_vars(scale))
            # 派生 amber 点缀色，避免 photo-placeholder 等渐变残留默认琥珀色
            overrides.update(_derive_amber_vars(scale))
            # cover-band 背景：取派生阶梯最深色（teal-900），与预设主题一致。
            # 直接覆盖（custom 显式给的 --bg-cover 会在 update(custom) 时覆盖回来）
            overrides["--bg-cover"] = (
                scale.get("--teal-900") or scale.get("--teal-800")
            )
    overrides.update(custom)
    overrides.pop("--primary", None)
    # --bg-cover 亮度兜底：LLM 传浅色时压深（cover-band 白字可读）
    _ensure_dark_cover(overrides)
    return overrides
