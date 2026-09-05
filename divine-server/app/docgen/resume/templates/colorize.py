"""简历模板换色：任意主色（中文色词 / #hex / rgb()）自动派生整套配色并注入模板 CSS。

背景：通用 PDF 管线（docgen/pdf/theme_colors.py）已支持"传一个主色自动派生整套配色"，
但简历模板库（templates/tXX）各自在 :root 里用不同的变量名定义品牌色
（--brand / --accent / --navy / --eu / --gold …），此前 color_scheme 参数在简历路径被丢弃。
本模块为简历做一份轻量、自包含的实现（不依赖 docgen.pdf，避免引入重模块）：

  1. 解析主色：色名表（含"石墨墨黑"等墨色系）+ #hex / rgb() / "色名 #hex"混合写法；
  2. HSL 派生四档：main（主色，压到适合白字阅读的亮度）/ dark / accent / soft；
  3. 按模板槽位表 RESUME_SLOTS 把派生色映射到该模板真实 CSS 变量，并把原主色/
     强调色的硬编码 hex 一并替换（覆盖 .toolbar 等未走变量的屏幕元素）；
  4. 追加 :root{...} 覆盖块；调用方显式 color_overrides（变量级）优先级最高。

未收录槽位表的老模板（boss_zhipin/finance/linkedin/kami/kami_white/minimal 等
无统一 :root 变量体系）不受影响，保持模板默认配色（优雅降级）。
"""

from __future__ import annotations

import colorsys
import re

# --------------------------------------------------------------------------
# 1. 颜色解析
# --------------------------------------------------------------------------

# 常用色名 → 基准色（与 docgen/pdf/theme_colors.COLOR_NAMES 同值，另补墨色/灰色系）
RESUME_COLOR_NAMES: dict[str, str] = {
    "red": "#E74C3C", "红色": "#E74C3C",
    "orange": "#E67E22", "橙色": "#E67E22",
    "yellow": "#D4A017", "黄色": "#D4A017",
    "green": "#27AE60", "绿色": "#27AE60",
    "cyan": "#1FA8A0", "青色": "#1FA8A0",
    "blue": "#2F5B9E", "蓝色": "#2F5B9E",
    "purple": "#5B4B8A", "紫色": "#5B4B8A",
    "pink": "#C94F7C", "粉色": "#C94F7C",
    "brown": "#8B5E3C", "棕色": "#8B5E3C",
    "teal": "#2A5A5B", "青绿": "#2A5A5B",
    "gray": "#555555", "grey": "#555555",
    "灰色": "#555555", "black": "#222222", "黑色": "#222222",
    "navy": "#1F3A5F", "藏青": "#1F3A5F", "藏蓝": "#1F3A5F",
    "酒红": "#7B2D3B", "墨绿": "#1F4A38", "森绿": "#2E6B4F",
    "天蓝": "#3B82C4", "靛蓝": "#3F51B5", "琥珀": "#B8743A",
    "金黄": "#D4A017", "珊瑚": "#E87A5D", "石板灰": "#4A5568",
    # 墨色/无彩色系（用户高频口语，如"石墨墨黑"）
    "石墨": "#2B2B2B", "石墨黑": "#2B2B2B", "墨黑": "#2B2B2B",
    "石墨墨黑": "#2B2B2B", "炭黑": "#333333", "煤黑": "#2E2E2E",
    "深灰": "#3A3A3A", "烟灰": "#555555", "银灰": "#8A8A8A",
    "浅灰": "#B8B8B8", "米灰": "#6E6A62",
}

_HEX_ONLY_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_RGB_RE = re.compile(
    r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$",
    re.IGNORECASE,
)
_ANY_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})\b")


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    match = _HEX_ONLY_RE.match((value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def resolve_color(value: str) -> tuple[int, int, int] | None:
    """把 色名 / #hex / rgb() / "色名 #hex" 混合写法统一解析为 RGB；失败返回 None。"""
    text = (value or "").strip()
    if not text:
        return None
    # 纯 #hex / rgb()
    rgb = _hex_to_rgb(text)
    if rgb:
        return rgb
    match = _RGB_RE.match(text)
    if match:
        r, g, b = (int(part) for part in match.groups())
        if all(0 <= ch <= 255 for ch in (r, g, b)):
            return (r, g, b)
    # 形如 "石墨墨黑(#2B2B2B)" / "深灰 #3A3A3A"：优先取句中 #hex
    for hex_match in _ANY_HEX_RE.finditer(text):
        digits = hex_match.group(1)
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
    # 纯中文/英文色名（容忍 "石墨墨黑配色" / "石墨墨黑" / 括号尾巴等写法）
    candidates = [text.lower()]
    bracketless = re.sub(r"[（(【\[].*$", "", text).strip().lower()
    if bracketless != candidates[0]:
        candidates.append(bracketless)
    suffixless = re.sub(r"(配色|色系|颜色|色|风格|款|调)$", "", bracketless).strip()
    if suffixless and suffixless != bracketless:
        candidates.append(suffixless)
    named = ""
    for key in candidates:
        named = RESUME_COLOR_NAMES.get(key)
        if named:
            break
    if not named:
        # 子串命中（仅中文色名，按名长优先，避免 "blue" 误中 "iceblue"）
        cjk_names = [n for n in RESUME_COLOR_NAMES if any(ord(c) > 127 for c in n)]
        for name in sorted(cjk_names, key=len, reverse=True):
            if name in candidates[0] or candidates[0] in name:
                named = RESUME_COLOR_NAMES[name]
                break
    return _hex_to_rgb(named) if named else None


# --------------------------------------------------------------------------
# 2. HSL 派生
# --------------------------------------------------------------------------


def _shift_lightness(
    rgb: tuple[int, int, int], lightness: float
) -> tuple[int, int, int]:
    """把 rgb 重映射到指定 HSL 亮度（保留色相/饱和度）。"""
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, _old_l, saturation = colorsys.rgb_to_hls(r, g, b)
    shifted = colorsys.hls_to_rgb(hue, min(max(lightness, 0.0), 1.0), saturation)
    return tuple(round(channel * 255) for channel in shifted)  # type: ignore[return-value]


def derive_resume_palette(rgb: tuple[int, int, int]) -> dict[str, str]:
    """从单一主色派生简历换色四档（返回 hex）。

    - main：主色。亮度过高（>0.50）时压到 0.45，保证头部/色带上的白字可读；
      本身已是深色（石墨墨黑/藏青等）则原样保留。
    - dark：主色再压深一档，用于侧栏等深色面（比 main 更深形成层次）。
    - accent：同色相提亮到可读档（浅底上的细线/标记）；无彩色系派生为灰阶。
    - soft：同色相极浅底色（标签/浅色块背景）。
    """
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    main_l = lightness if lightness <= 0.50 else 0.45
    main = colorsys.hls_to_rgb(hue, main_l, saturation)
    main_rgb = tuple(round(ch * 255) for ch in main)  # type: ignore[arg-type]

    accent_l = min(max(main_l + 0.18, 0.36), 0.60)
    soft_l = 0.93
    soft_s = min(saturation, 0.55)
    accent = colorsys.hls_to_rgb(hue, accent_l, saturation)
    soft = colorsys.hls_to_rgb(hue, soft_l, soft_s)
    return {
        "main": _rgb_to_hex(main_rgb),  # type: ignore[arg-type]
        "dark": _rgb_to_hex(_shift_lightness(main_rgb, max(main_l - 0.08, 0.08))),  # type: ignore[arg-type]
        "accent": _rgb_to_hex(
            tuple(round(ch * 255) for ch in accent)  # type: ignore[arg-type]
        ),
        "soft": _rgb_to_hex(tuple(round(ch * 255) for ch in soft)),  # type: ignore[arg-type]
    }


# --------------------------------------------------------------------------
# 3. 模板槽位表
# --------------------------------------------------------------------------

# template_id -> {token: [该模板真实 CSS 变量, ...]}
# token 语义：main=头部/标题/条带主色；dark=更深主色面（侧栏）；accent=强调色；soft=浅底
RESUME_SLOTS: dict[str, dict[str, list[str]]] = {
    "tpl_professional": {"main": ["--accent"]},
    "tpl_modern": {"main": ["--brand"], "soft": ["--brand-soft"]},
    "tpl_academic": {"main": ["--accent"]},
    "tpl_executive": {"main": ["--navy"], "accent": ["--gold"]},
    "tpl_creative": {"main": ["--accent"]},
    "tpl_product": {"main": ["--brand"], "soft": ["--brand-soft"]},
    "tpl_data": {"main": ["--brand"], "soft": ["--brand-soft"]},
    "tpl_freshgrad": {"main": ["--brand"], "soft": ["--brand-soft"]},
    "tpl_lateral": {"main": ["--brand"], "soft": ["--brand-soft"]},
    "tpl_compact": {"main": ["--brand"], "dark": ["--side"]},
    "tpl_global": {"main": ["--eu"], "soft": ["--eu-soft"]},
    "creative": {"main": ["--brand"], "soft": ["--brand-soft"]},
}

_VAR_RE = re.compile(r"^--[A-Za-z0-9_-]+$")
_COLOR_VALUE_RE = re.compile(r"^[#A-Za-z0-9(),.%\s\-]+$")


def _root_default(css: str, var_name: str) -> str | None:
    """从模板 CSS 的 :root 里取某变量的默认值（用于旧色硬编码替换）。"""
    match = re.search(
        re.escape(var_name) + r"\s*:\s*([^;}]+)", css, re.IGNORECASE
    )
    return match.group(1).strip() if match else None


def _is_color(value: str) -> bool:
    return bool(value and _COLOR_VALUE_RE.match(value) and _hex_to_rgb(value))


def apply_resume_color(
    css: str,
    template_id: str,
    *,
    color_scheme: str | None = None,
    color_overrides: dict[str, str] | None = None,
) -> str:
    """返回注入配色后的 CSS（无配色或无法解析时原样返回）。

    - color_scheme：主色描述（中文色词 / #hex / rgb()），自动派生整套；
    - color_overrides：CSS 变量级直接覆盖 {"--navy": "#2B2B2B"}，优先级最高。
    """
    if not color_scheme and not color_overrides:
        return css

    css = css or ""
    var_overrides: dict[str, str] = {}
    literal_map: dict[str, str] = {}  # 旧 hex -> 新 hex（替换硬编码旧主色）

    if color_scheme:
        rgb = resolve_color(color_scheme)
        slots = RESUME_SLOTS.get(template_id)
        if rgb and slots:
            palette = derive_resume_palette(rgb)
            token_vars: dict[str, list[str]] = {
                "main": slots.get("main", []),
                "dark": slots.get("dark", []),
                "accent": slots.get("accent", []),
                "soft": slots.get("soft", []),
            }
            for token, var_names in token_vars.items():
                new_value = palette[token]
                for var_name in var_names:
                    old_default = _root_default(css, var_name)
                    var_overrides[var_name] = new_value
                    if _is_color(old_default or ""):
                        literal_map[old_default.upper()] = new_value  # type: ignore[arg-type]

    # 显式变量级覆盖（最高优先级，且不触发旧色字面替换）
    if color_overrides:
        for key, value in color_overrides.items():
            key = str(key).strip()
            value = str(value).strip()
            if not _VAR_RE.match(key) or not value or not _COLOR_VALUE_RE.match(value):
                continue
            var_overrides[key] = value

    if not var_overrides:
        return css

    # 旧主色/强调色硬编码处（.toolbar 等屏幕元素、未走变量的同类 hex）同步替换
    if literal_map:
        def _replace(match: re.Match[str]) -> str:
            token = match.group(0)
            return literal_map.get(token.upper(), token)

        css = _ANY_HEX_RE.sub(_replace, css)

    block = ":root{" + "".join(f"{k}:{v};" for k, v in var_overrides.items()) + "}"
    return css.rstrip() + "\n" + block + "\n"
