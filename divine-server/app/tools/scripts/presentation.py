import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.ppt.normalize import normalize_slides  # noqa: E402
from app.docgen.ppt.renderer import get_ppt_theme  # noqa: E402
from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.tools.scripts.svg_common import render_svg_to_png  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg"}


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".pptx"):
        cleaned += ".pptx"
    return cleaned


def _is_cover_slide(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    # 显式声明 layout=cover 也算封面（否则会被当成内容页，再多生成一张自动封面）
    if str(item.get("layout") or "").strip().lower() == "cover":
        return True
    return bool(
        item.get("subtitle")
        and not item.get("points")
        and not item.get("bullets")
        and not item.get("list")
        and not item.get("body")
        and not item.get("content")
        and not item.get("text")
        and not item.get("layout")
    )


def _devconf_slot_of(item: dict) -> str:
    """把一个大纲条目分类到 016 配方槽位；不属于任何槽位返回 ""。"""
    layout = str(item.get("layout") or "").strip().lower()
    heading = str(item.get("heading") or item.get("title") or "").strip().lower()
    if layout == "section":
        return "manifesto"
    if layout in ("compare", "table"):
        return "vs"
    if layout == "kpi":
        if re.search(r"增长|growth|注册|用户规模", heading):
            return "growth"
        return "numbers"
    if layout == "chart":
        # 增长曲线类图表对应 016 P8 增长页；其余图表不属标准页序
        return "growth" if re.search(r"增长|growth", heading) else ""
    if layout == "two_col":
        if re.search(r"全景|架构|看懂|一览|overview|认识", heading):
            return "overview"
        return "deepdive"
    if layout in ("cards", "columns"):
        if re.search(r"全景|架构|看懂|一览|overview", heading):
            return "overview"
        if re.search(r"留存|retention|nps|引擎|续费", heading):
            return "retention"
        return "features"
    # 普通 bullets/timeline 不占用 overview 槽（016 P4 是产品全景专属页）：
    # 命中"理由/选择"进 why，否则作为额外内容追加在收尾前
    if layout in ("bullets", "timeline"):
        if re.search(r"理由|why|选择|为什么|为何", heading):
            return "why"
        return ""
    return ""


# 016 固定页面配方：槽位顺序即页序（cover 与 end 在装配层单独处理）。
# 每槽 (槽位名, 页面标签, 容量, 占位条目工厂)。缺失槽位按占位页补齐，
# 保证生成的 deck 结构与样张 100% 一致，用户往 {{占位}} 里填内容即可。
def _devconf_placeholder(slot: str, brand: str) -> dict:
    b = brand or "{{品牌名}}"
    # kicker 只写纯文案：渲染器 _head_devconf 自动加「NN ·」页序前缀
    table: dict[str, dict] = {
        "manifesto": {"layout": "section", "heading": "{{品牌使命一句话：我们相信……}}",
                      "kicker": "Brand", "points": ["{{关键词一}}", "{{关键词二}}", "{{关键词三}}"],
                      "brand": b},
        # 016 P3：每格只有大数值+标签（delta 胶囊是 P8 增长页元素），底部为长句背书
        "numbers": {"layout": "kpi", "heading": "用数字认识我们", "kicker": "Brand by Numbers",
                    "points": ["{{120万+}}|{{注册用户（截至 {{2026.09}}）}}",
                               "{{40万}}|{{月活跃用户}}",
                               "{{18个月}}|{{连续保持 {{xx%}} 月复合增长}}",
                               "{{4.9}}|{{应用商店评分（{{N}} 条评价）}}"],
                    "subtitle": "{{一句话品牌背书：}}成立于 {{年份}}，由 {{背景}} 团队打造；"
                                "{{产品}} 以 {{核心理念}} 服务 {{目标人群}}，被 {{标杆客户/社区}} 广泛推荐。"},
        # 016 P4：head + 通栏架构图占位框 + 底部一行聚焦 cap
        "overview": {"layout": "overview", "heading": f"一张图看懂 {b}", "kicker": "Product Overview",
                     "subtitle": "{{「产品定位一句话」——N 大模块，N 项核心能力。}}",
                     "points": ["本次大会聚焦：|{{模块 A}} 与 {{模块 B}} 两大方向的 {{N}} 项新能力。"]},
        "features": {"layout": "cards", "heading": "六大亮点功能", "kicker": "Highlights",
                     "points": [f"{{{{功能 {i}}}}}|{{{{一句话价值}}}}" for i in range(1, 7)]},
        "deepdive1": {"layout": "two_col", "image_side": "left", "heading": "{{亮点深潜 1：核心主张}}", "kicker": "Deep Dive",
                      "subtitle": "{{两句话说明这个能力解决什么问题}}",
                      "points": ["{{要点一}}|{{补充说明}}", "{{要点二}}|{{补充说明}}", "{{要点三}}|{{补充说明}}"]},
        "deepdive2": {"layout": "two_col", "image_side": "right", "heading": "{{亮点深潜 2：核心主张}}", "kicker": "Deep Dive",
                      "subtitle": "{{两句话说明这个能力解决什么问题}}",
                      "points": ["{{要点一}}|{{补充说明}}", "{{要点二}}|{{补充说明}}", "{{要点三}}|{{补充说明}}"]},
        # 016 P8：左侧 88px 大数字 + delta 胶囊，右侧圆角图表框（柱状/截图占位）
        "growth": {"layout": "growth", "heading": "用户增长", "kicker": "Growth",
                   "chart_title": "{{季度注册用户趋势}}",
                   "points": ["{{120万}}|{{累计注册用户}}|YoY +{{180%}}"],
                   "chart": {"type": "column",
                             "categories": ["{{24Q2}}", "{{24Q4}}", "{{25Q2}}",
                                            "{{25Q4}}", "{{26Q2}}", "{{26Q3}}"],
                             "series": [{"name": "{{注册用户}}",
                                         "values": [18, 26, 38, 57, 83, 120]}]}},
        # 016 P9 是组合页：KPI 三栏（数据带同款）+ a/b/c 增长引擎列表
        "retention": {"layout": "kpi_rows", "heading": "增长的背后是留存", "kicker": "Growth Metrics",
                      "points": ["{{62}}%|{{次月留存率}}|{{+9pp}} YoY",
                                 "{{71}}%|{{周活跃占比}}|{{+6pp}} YoY",
                                 "{{4.9}}|{{用户满意度}}|NPS {{72}}",
                                 "{{增长引擎一}}|{{描述驱动力，如口碑推荐占比 {{xx%}}。}}",
                                 "{{增长引擎二}}|{{描述驱动力，如 {{生态集成}} 带来的自然流量。}}",
                                 "{{增长引擎三}}|{{描述驱动力，如 {{开发者社区}} 的 {{N}} 个第三方扩展。}}"]},
        # 016 P10 是 mono 表头对比表（我们列蓝色高亮 + ✓/✕），不是双栏卡片
        "vs": {"layout": "table", "heading": "与主流方案对比", "kicker": "Compare",
               "subtitle": "注：{{对比基于公开资料，截至 {{日期}}}}",
               "table": {"columns": ["能力维度", b, "{{竞品 A}}", "{{竞品 B}}"],
                         "rows": [["{{核心能力}}", "{{一句话优势描述}}", "{{描述}}", "{{描述}}"],
                                  ["{{开放性 / 扩展}}", "✓ {{开放生态 + 插件体系}}", "✕ {{封闭}}", "✓ {{部分开放}}"],
                                  ["{{本地化 / 隐私}}", "✓ {{本地优先}}", "✕ {{仅云端}}", "✕ {{仅云端}}"],
                                  ["{{价格}}", "{{免费档 + 透明定价}}", "{{定价描述}}", "{{定价描述}}"],
                                  ["{{开发者体验}}", "✓ {{CLI + API + 文档}}", "{{描述}}", "{{描述}}"]]}},
        "why": {"layout": "bullets", "heading": f"三个选择 {b} 的理由", "kicker": "Why Us",
                "points": ["{{理由一：核心主张}}|{{两句话展开：差异化的产品决策 + 用户可感知的结果。}}|{{关键数据 / 口径}}",
                           "{{理由二：核心主张}}|{{两句话展开：{{API / 生态 / 文档}} 的投入与社区反馈。}}|{{GitHub {{N}}k Stars · {{N}} 个插件}}",
                           "{{理由三：核心主张}}|{{两句话展开：{{本地优先 / 加密 / 合规}} 承诺。}}|{{SOC 2 · {{本地模式}}}}"]},
    }
    return table[slot]


def _compare_to_table(item: dict) -> dict:
    """016 P10 对比页是表格而非双栏卡：compare 条目转换为 mono 表头对比表。
    行 = 左侧能力点；我们列 ✓ + 补充，对方列 ✕ + 对方能力点。"""
    left = item.get("left") or {}
    right = item.get("right") or {}

    def _pairs(side: dict) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for raw in side.get("points") or []:
            text = str(raw)
            a, _, b2 = text.partition("|")
            out.append((a.strip(), b2.strip()))
        return out

    lp, rp = _pairs(left), _pairs(right)
    rows: list[list[str]] = []
    for i in range(max(len(lp), len(rp))):
        l_label, l_note = lp[i] if i < len(lp) else ("", "")
        r_label, r_note = rp[i] if i < len(rp) else ("", "")
        rows.append([l_label or "{{能力}}",
                     f"✓ {l_note or l_label or '{{优势}}'}".strip(),
                     f"✕ {r_note or r_label or '{{描述}}'}".strip()])
    return {"layout": "table",
            "heading": str(item.get("heading") or item.get("title") or "与主流方案对比"),
            "kicker": str(item.get("kicker") or "Compare"),
            "subtitle": str(item.get("subtitle") or ""),
            "table": {"columns": ["能力维度", str(left.get("title") or "{{本品}}"),
                                  str(right.get("title") or "{{对比方案}}")],
                      "rows": rows}}


_DEVCONF_SLOTS: list[tuple[str, str, int]] = [
    ("manifesto", "品牌使命宣言", 1),
    ("numbers", "品牌数据带", 1),
    ("overview", "产品全景", 1),
    ("features", "亮点功能总览", 1),
    ("deepdive1", "亮点深潜 1", 1),
    ("deepdive2", "亮点深潜 2", 1),
    ("growth", "用户增长", 1),
    ("retention", "留存与口碑", 1),
    ("vs", "竞品对比", 1),
    ("why", "选择理由", 1),
]


def _apply_devconf_recipe(items: list, brand: str, warnings: list[str]) -> list:
    """devconf 固定配方装配：与 006 pop 一样 100% 按样张结构出页。

    大纲条目按槽位匹配填入；缺失槽位输出 {{占位}} 页（用户补充即可）；
    未匹配内容追加在收尾页之前，不静默丢弃；toc 页丢弃（样张无目录）。
    """
    buckets: dict[str, list] = {}
    extras: list = []
    # 显式 end 页不参与槽位分类，装配完成后放回末尾
    end_item = None
    if items and isinstance(items[-1], dict) \
            and str(items[-1].get("layout") or "").strip().lower() == "end":
        end_item = items.pop()
    for it in items:
        if isinstance(it, dict) and str(it.get("layout") or "").strip().lower() == "toc":
            warnings.append("已忽略目录页（devconf 模板无目录页）")
            continue
        slot = _devconf_slot_of(it) if isinstance(it, dict) else ""
        cap = {"deepdive": 2}.get(slot, 1)
        if slot and len(buckets.get(slot, [])) < cap:
            buckets.setdefault(slot, []).append(it)
        else:
            extras.append(it)
    deck: list = []
    for slot, label, _cap in _DEVCONF_SLOTS:
        key = "deepdive" if slot.startswith("deepdive") else slot
        pool = buckets.get(key) or []
        if pool:
            picked = pool.pop(0)
            if slot == "vs" and str(picked.get("layout") or "").lower() == "compare":
                # 016 P10 是表格：compare 双栏条目转 mono 表头对比表
                picked = _compare_to_table(picked)
            if slot == "overview" and str(picked.get("layout") or "").lower() != "overview":
                # 016 P4 是通栏架构图页：统一转 overview（首条点作底部聚焦 cap）
                picked = {**picked, "layout": "overview"}
            if slot == "growth" and str(picked.get("layout") or "").lower() != "growth":
                # 016 P8 是左大数字 + 右图表的组合页：统一转 growth
                picked = {**picked, "layout": "growth"}
            if slot.startswith("deepdive"):
                # 016 P6 图左 / P7 图右镜像：未显式指定时按槽位注入
                picked.setdefault("image_side", "left" if slot == "deepdive1" else "right")
            if slot == "retention" and str(picked.get("layout") or "").lower() != "kpi_rows":
                # 016 P9 是 KPI 三栏 + 引擎列表组合页：统一转 kpi_rows；
                # 大纲点的前 3 条作 KPI（'数值|标签|涨跌'），其余作引擎行
                pts = [str(p) for p in (picked.get("points") or [])]
                picked = {**picked, "layout": "kpi_rows", "points": pts}
            deck.append(picked)
        else:
            deck.append(_devconf_placeholder(slot, brand))
            warnings.append(f"「{label}」页在大纲中缺失，已按模板输出占位页（{{{{占位}}}}），请补充内容")
    # 未匹配内容（quote/额外页）追加在结尾页之前，不静默丢弃
    if extras:
        deck.extend(extras)
        warnings.append(f"{len(extras)} 页大纲内容不属于模板标准页序，已追加在收尾页之前")
    if end_item is not None:
        deck.append(end_item)
    return deck


def _keynote_slot_of(item: dict) -> str:
    """015 配方槽位分类：manifesto/reveal/features/stats/vs/ecosystem/pricing。"""
    layout = str(item.get("layout") or "").strip().lower()
    heading = str(item.get("heading") or item.get("title") or "").strip().lower()
    if layout == "section":
        return "manifesto"
    if layout in ("table", "compare"):
        return "vs"
    if layout == "kpi":
        return "stats"
    if layout in ("cards", "columns"):
        return "features"
    if layout == "pricing":
        return "pricing"
    if layout in ("quote", "two_col"):
        if re.search(r"亮相|登场|发布|introducing|新品", heading):
            return "reveal"
        return ""
    if layout in ("bullets", "timeline"):
        if re.search(r"生态|互联|全家桶|ecosystem", heading):
            return "ecosystem"
        return ""
    return ""


_KEYNOTE_SLOTS: list[tuple[str, str]] = [
    ("manifesto", "愿景宣言"),
    ("reveal", "产品亮相"),
    ("features", "特性三卡"),
    ("stats", "性能数据"),
    ("vs", "对比"),
    ("ecosystem", "生态"),
    ("pricing", "价格·发售"),
]


def _keynote_placeholder(slot: str, brand: str) -> dict:
    b = brand or "{{品牌名}}"
    table: dict[str, dict] = {
        "manifesto": {"layout": "section", "heading": "{{一句话愿景：我们相信……}}",
                      "kicker": "{{Mission}}", "points": ["{{关键词一}}", "{{关键词二}}"],
                      "brand": b},
        "reveal": {"layout": "reveal", "kicker": "{{全新登场}}",
                   "heading": f"{b}|{{{{产品系列名}}}}",
                   "subtitle": "{{一句话卖点，如：把旗舰影像与端侧大模型装进 7.9 毫米机身。}}",
                   "feature": "{{产品定位，如 AI 全面屏旗舰}}"},
        "features": {"layout": "cards", "heading": "{{一部设备，三种从容}}",
                     "kicker": "{{产品名}} · 三大核心",
                     "points": ["{{能力一}}|{{一句话说明}}", "{{能力二}}|{{一句话说明}}",
                                "{{能力三}}|{{一句话说明}}"]},
        "stats": {"layout": "kpi", "heading": "{{数据，不会说谎}}",
                  "kicker": "{{产品名}} · 性能",
                  "points": ["{{52}}|{{降噪深度}}|{{自适应主动降噪}}",
                             "{{360}}|{{空间音频}}|{{头部追踪}}",
                             "{{40+}}|{{语种}}|{{实时翻译}}"]},
        "vs": {"layout": "table", "heading": "{{每一代，都更懂你}}",
               "kicker": "Compare · 全维度升级",
               "subtitle": "注：{{数据来自实验室测试，实际表现因使用环境而异。}}",
               "table": {"columns": ["维度", b, "{{上代产品}}", "{{竞品代表}}"],
                         "rows": [["{{核心芯片}}", "{{新一代芯片}}", "{{上代芯片}}", "{{竞品芯片}}"],
                                  ["{{屏幕}}", "{{参数}}", "{{参数}}", "{{参数}}"],
                                  ["{{影像}}", "{{参数}}", "{{参数}}", "{{参数}}"],
                                  ["{{续航}}", "{{参数}}", "{{参数}}", "{{参数}}"]]}},
        "ecosystem": {"layout": "ecosystem", "heading": f"不止是一台 {{{{产品}}}}",
                      "kicker": "Ecosystem · 生态协同",
                      "subtitle": "{{与全家桶的每一次相遇，都恰到好处。}}",
                      "points": ["{{手表联动}}|{{一句话描述}}", "{{耳机接力}}|{{一句话描述}}",
                                 "{{云同步}}|{{一句话描述}}"]},
        "pricing": {"layout": "pricing", "heading": "现在，|触手可及。",
                    "kicker": "Pricing · 价格与发售",
                    "points": ["{{Phone}}|{{产品名称 标准版}}|{{配置}}|¥{{3,999}}",
                               "{{Pro · 推荐}}|{{产品名称}} Pro|{{配置 · 首发权益}}|¥{{4,999}}",
                               "{{Pro Max}}|{{产品名称}} Pro Max|{{配置}}|¥{{5,999}}"],
                    "subtitle": "{{开售时间}} · {{渠道}} · 敬请期待"},
    }
    return table[slot]


def _apply_keynote_recipe(items: list, brand: str, warnings: list[str]) -> list:
    """015 固定 8 页配方装配（与 devconf 同机制）：槽位匹配 + 缺失补 {{占位}} 页。"""
    buckets: dict[str, list] = {}
    extras: list = []
    # 显式 end 页视作价格·发售收尾页的内容来源（015 无独立结尾页）
    if items and isinstance(items[-1], dict) \
            and str(items[-1].get("layout") or "").strip().lower() == "end":
        end_item = items.pop()
        buckets.setdefault("pricing", []).append(
            {**end_item, "layout": "pricing"})
    for it in items:
        if isinstance(it, dict) and str(it.get("layout") or "").strip().lower() == "toc":
            warnings.append("已忽略目录页（keynote 模板无目录页）")
            continue
        slot = _keynote_slot_of(it) if isinstance(it, dict) else ""
        if slot and len(buckets.get(slot, [])) < 1:
            buckets.setdefault(slot, []).append(it)
        else:
            extras.append(it)
    deck: list = []
    for slot, label in _KEYNOTE_SLOTS:
        pool = buckets.get(slot) or []
        if pool:
            picked = pool.pop(0)
            if slot == "vs" and str(picked.get("layout") or "").lower() == "compare":
                tbl = picked.get("table")
                if isinstance(tbl, dict) and tbl.get("columns"):
                    # 用户已传真实表格数据：保留原表（勿用 left/right 重建）
                    picked = {**picked, "layout": "table"}
                else:
                    # 015 P6 暗色表格：compare 双栏转表（本品列粗体）
                    picked = _compare_to_table(picked)
            deck.append(picked)
        else:
            deck.append(_keynote_placeholder(slot, brand))
            warnings.append(f"「{label}」页在大纲中缺失，已按模板输出占位页（{{{{占位}}}}），请补充内容")
    if extras:
        deck = deck[:-1] + extras + [deck[-1]]  # 追加内容放在价格页之前
        warnings.append(f"{len(extras)} 页大纲内容不属于模板标准页序，已追加在价格页之前")
    return deck

def _resolve_inside(root: Path, raw: str) -> Path | None:
    """把相对/绝对路径解析到 root 内；越界返回 None。"""
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _make_media_resolver(workspace: Path, output_root: Path):
    """图片路径解析与 SVG→PNG 转换；不可用图片返回 None（版式侧降级占位）。"""

    def resolve(raw: str) -> Path | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        source = _resolve_inside(workspace, raw)
        if source is None and raw.startswith("/"):
            source = _resolve_inside(output_root, raw)
        if source is None or not source.is_file():
            return None
        if source.suffix.lower() not in IMAGE_EXTS:
            return None
        if source.suffix.lower() != ".svg":
            return source
        # SVG：转 PNG 后插入（复用 svg_to_png 的渲染链）
        with tempfile.TemporaryDirectory(prefix="ppt_media_") as tmp:
            target = Path(tmp) / f"{source.stem}.png"
            ok, _ = render_svg_to_png(source, target)
            if not ok:
                return None
            # 移出临时目录，保证 pptx 打开读取时文件仍存在
            persist_dir = output_root / "media_cache"
            persist_dir.mkdir(parents=True, exist_ok=True)
            persisted = persist_dir / f"{source.stem}_{abs(hash(str(source))) % 10**8}.png"
            shutil.move(str(target), str(persisted))
            return persisted

    return resolve


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    output_root = Path(data.get("output_dir") or workspace)
    params = data.get("params") or {}
    title = str(params.get("title") or "未命名演示文稿")
    theme_id = str(params.get("theme") or params.get("style") or "universal").strip()
    get_ppt_theme(theme_id)  # 未知主题回退默认，不报错
    # 主题色覆盖：theme_colors 只需 {"--color-primary": "<颜色>"}，
    # 支持颜色名/色值（与 PDF 工具约定一致）；对所有主题生效
    theme_colors = params.get("theme_colors") or {}
    primary = ""
    if isinstance(theme_colors, dict):
        primary = str(theme_colors.get("--color-primary")
                      or theme_colors.get("--primary") or "").strip()
    ppt_theme = None
    if primary:
        from app.docgen.ppt.renderer.themes import apply_primary_color
        ppt_theme = apply_primary_color(dict(get_ppt_theme(theme_id)), primary)
    raw_path = str(params.get("path") or "").strip()

    # 归一化层（docs/fix/001-ppt-empty-slides-20260906.md §4.1）：items/quote/bullets 等别名键
    # 收敛到渲染器窄键；未识别键进 warnings，不再静默丢弃。
    slides, warnings = normalize_slides(params.get("slides") or [])

    output_dir = output_root / "presentations"
    if raw_path:
        # path 语义是"保存目录"，但模型常把它当文件路径传 …xxx.pptx——
        # 防御性剥离文件名，只取父目录（避免建出名叫 xxx.pptx 的目录）。
        if raw_path.lower().endswith((".pptx", ".ppt")):
            parent = str(Path(raw_path).parent)
            warnings.append(f"path 参数含文件名，已按目录处理：取 {parent or 'workspace 根目录'}")
            raw_path = parent
        candidate = _resolve_inside(workspace, raw_path) if raw_path not in ("", ".") else None
        if raw_path and candidate is None:
            print(json.dumps(
                {"success": False, "message": f"保存路径越界: {raw_path}"},
                ensure_ascii=False,
            ))
            return
        if candidate is not None:
            output_dir = candidate
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "演示文稿", ".pptx")

    from pptx import Presentation

    from app.docgen.ppt.renderer import SLIDE_H, SLIDE_W
    from app.docgen.ppt.renderer.layouts import guess_layout

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    resolve_media = _make_media_resolver(workspace, output_root)
    items = list(slides)
    # 样张主题标记提前计算：封面兜底与配方装配都要用
    sample_mode = (ppt_theme or get_ppt_theme(theme_id)).get("sample") or ""
    if items and _is_cover_slide(items[0]):
        cover = dict(items[0])
        cover["layout"] = "cover"
        cover.setdefault("heading", title)
        # 封面元信息兜底：LLM 漏传 brand/event/kicker 时至少保证品牌行不空
        cover.setdefault("brand", title)
        if sample_mode == "devconf":
            # 016 封面四件套缺省占位：缺什么显示什么占位，用户一眼可见待填项
            cover.setdefault("event", "{{EVENT 2026}}")
            cover.setdefault("kicker", "Product Keynote")
            cover.setdefault("date", "{{日期}}")
            cover.setdefault("place", "{{发布场地 / 线上直播}}")
        cover_items = [cover]
        items = items[1:]
    else:
        subtitle = str(items[0].get("subtitle") or "") if items and isinstance(items[0], dict) else ""
        cover_items = [{
            "layout": "cover", "heading": title, "subtitle": subtitle,
        }]

    # 结尾页兜底：用户未显式给出 end 页时自动补一页
    last_layout = str(items[-1].get("layout") or "").strip().lower() if items and isinstance(items[-1], dict) else ""
    if items and last_layout != "end":
        if sample_mode == "devconf":
            # 016 P12 是 CTA 版式（_end_devconf）：品牌行 + 行动号召 + 双胶囊按钮 + mono 联系行
            items = items + [{"layout": "end",
                              "heading": "现在就开始创造",
                              "subtitle": "{{官网 / 下载渠道}}",
                              "brand": str((cover_items[0] or {}).get("brand") or title),
                              "points": ["{{立即体验}}", "{{View Docs}}"],
                              "body": "{{联系邮箱 / 社区入口}}"}]
        elif sample_mode == "keynote":
            pass  # 015 P8 价格·发售即收尾页，由配方装配补齐，不再追加通用结尾页
        else:
            items = items + [{"layout": "end", "heading": "谢谢观看"}]

    # 样张主题装配（docs/design：006 pop 的经验——结构固定才能 100% 还原样张）
    suppress_toc = False
    deck_brand = str((cover_items[0] or {}).get("brand") or title) if cover_items else title
    if sample_mode == "devconf":
        # 016 固定 12 页配方：槽位匹配大纲，缺失槽位补 {{占位}} 页，缺什么补什么
        items = _apply_devconf_recipe(items, deck_brand, warnings)
        suppress_toc = True
    elif sample_mode == "keynote":
        # 015 固定 8 页配方装配：槽位匹配 + 缺失补 {{占位}} 页（价格页即收尾）
        items = _apply_keynote_recipe(items, deck_brand, warnings)
        suppress_toc = True

    # 目录页兜底：未显式给出且内容量足够时，按章节页自动生成（含页码）
    def _is_toc(it: dict) -> bool:
        return (str(it.get("layout") or "").strip().lower() == "toc"
                or "目录" in str(it.get("heading") or ""))

    want_toc = params.get("toc")
    if suppress_toc:
        want_toc = False  # 样张主题无目录页：显式 toc=true 也忽略
    has_toc = any(isinstance(it, dict) and _is_toc(it) for it in items)
    sections = [(i, str(it.get("heading") or it.get("title") or "").strip())
                for i, it in enumerate(items)
                if isinstance(it, dict)
                and str(it.get("layout") or "").strip().lower() == "section"
                and str(it.get("heading") or it.get("title") or "").strip()]
    toc_inserted = False
    if not has_toc and want_toc is not False:
        if want_toc is True or (len(items) >= 5 and len(sections) >= 2):
            if len(sections) >= 2:
                entries = [f"{heading}|P{i + 3:02d}"
                           for i, heading in sections[:8]]
            else:  # 强制开启但章节不足：均匀取样内容页标题
                pool = [str(it.get("heading") or it.get("title") or "").strip()
                        for it in items
                        if isinstance(it, dict)
                        and str(it.get("layout") or "").strip().lower()
                        not in ("end", "section", "cover")
                        and str(it.get("heading") or it.get("title") or "").strip()]
                step = max(1, len(pool) // 8)
                entries = pool[::step][:8]
            if entries:
                items = [{"layout": "toc", "heading": "目录",
                          "points": entries}] + items
                toc_inserted = True

    from app.docgen.ppt.renderer.layouts import add_slide

    total_pages = len(cover_items) + len(items)
    # 总页数挂到每个 item 上：内容页的页码/进度点也需要（此前只挂封面项，
    # 导致 pop 风格的内容页页脚拿不到总数而退回标题摘要）
    if cover_items and isinstance(cover_items[0], dict):
        deck_brand = str(cover_items[0].get("brand") or "") or deck_brand
    for it in cover_items + items:
        if isinstance(it, dict):
            it["_pages"] = total_pages
            it["_brand"] = deck_brand
    rendered = 0
    rendered_layouts: list[str] = []
    try:
        for item in cover_items + items:
            rendered_layouts.append(
                add_slide(prs, item, theme_id, rendered + 1,
                          resolve_media=resolve_media, theme=ppt_theme)
            )
            rendered += 1
    except ValueError as exc:
        print(json.dumps(
            {"success": False, "message": str(exc)},
            ensure_ascii=False,
        ))
        return

    prs.save(output_path)

    # 渲染后质检（docs/fix/001-ppt-empty-slides-20260906.md §4.3）：重开自检 + 内容版式空页检测
    from app.docgen.ppt.qa import qa_slides

    warnings.extend(qa_slides(output_path, cover_items + items, rendered_layouts))
    empty_pages = [w for w in warnings if "内容为空" in w]
    message = "PPT 生成完成"
    if empty_pages:
        message = f"PPT 已生成，但检测到 {len(empty_pages)} 页内容为空或过少，建议补充后重新生成"

    from app.docgen.ppt.renderer import PPT_THEMES
    from app.docgen.ppt.renderer.themes import STYLES
    print(json.dumps(
        {
            "success": True,
            "message": message,
            "file_name": output_path.name,
            "filepath": str(output_path),
            "content": message
            + ("。质检提示：" + "；".join(warnings) if warnings else ""),
            "data": {
                "theme": theme_id,
                "slides": rendered,
                "toc": toc_inserted,
                "presets": len(PPT_THEMES),
                "styles": sorted(STYLES),
                "warnings": warnings,
            },
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
