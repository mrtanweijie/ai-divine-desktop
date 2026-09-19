from __future__ import annotations

import html as html_lib
import re

from .base import MODULE_GUIDE, PDFIntent, PDFRecipe
from .travel_html import closing_pages_html


# ---------------------------------------------------------------------------
# 页式模板提示词的公共片段
#
# 抽取原则：只收敛**逐字相同**的部分（角色句、骨架块、输出规则分隔线），
# 各配方的规则正文保持独立——travel 的提示词是长期调过的，
# 不为省几行重复去改动它的措辞。改动后须用
# 「travel 提示词前后快照比对」验证为逐字一致。
# ---------------------------------------------------------------------------

def _load_skeleton(
    theme: str, fallback_name: str | None = None
) -> tuple[str, str]:
    """取模板骨架与其文件名，返回 (skeleton, skeleton_name)。"""
    from .theme_manager import html_template_skeleton
    from .theme_registry import THEMES

    skeleton = html_template_skeleton(theme)
    name = THEMES.get(theme, {}).get("file") or fallback_name or theme
    return skeleton, name


def _skeleton_prompt(
    role: str, desc: str, skeleton: str, skeleton_name: str
) -> str:
    """页式模板提示词开头：角色句 + 骨架块 + 输出规则分隔线。

    role 例：「旅行手册作者」「数据分析报告撰稿人」
    desc 例：「现代风格旅行攻略」「完整旅行攻略」「」（四套论文/报告不填）
    desc 为空时只保留一个空格，避免拼出「PDF 的 完整旅行攻略」这类多余空格
    （travel 提示词的措辞是长期调过的，改提示词必须走前后快照比对）。
    """
    # 「的」后直接接修饰语，修饰语与 HTML 之间留一个空格；desc 为空时退化为一个空格
    spacer = f"{desc} " if desc else " "
    return (
        "你是资深"
        + role
        + "。严格按下述【模板骨架】的页面结构与 CSS 类名，"
        f"输出一份可直接打印为 PDF 的{spacer}HTML body。\n"
        f"══════════════ 模板骨架（{skeleton_name}） ══════════════\n"
        + skeleton
        + "\n══════════════ 输出规则 ══════════════\n"
    )


class ReportRecipe(PDFRecipe):
    name = "report"
    display_name = "报告"
    css_template = "universal"
    color_scheme = "blue"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "报告主题", '
        '"sections": [{"title": "章节", "key_points": ["要点"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是技术分析师和商务报告作者。根据文档结构生成专业报告 Markdown。\n"
            "要求：包含摘要、背景、分析、结论；关键数据用表格或要点；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"报告主题：{intent.topic}"
            + MODULE_GUIDE
        )


class BusinessAnalysisRecipe(PDFRecipe):
    name = "business"
    display_name = "商业分析报告"
    css_template = "universal"
    color_scheme = "blue"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "品牌/行业与要回答的商业问题", '
        '"brand": "分析的品牌名（未知可省略）", "industry": "所属行业（可省略）", '
        '"competitors": ["对标品牌1", "对标品牌2"], '
        '"sections": [{"title": "章节", "key_points": ["要点"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        brand = str(meta.get("brand") or "").strip()
        industry = str(meta.get("industry") or "").strip()
        competitors = meta.get("competitors")
        competitor_text = (
            "、".join(str(item) for item in competitors)
            if isinstance(competitors, list) and competitors
            else ""
        )
        subject = "、".join(
            part for part in (brand, industry, competitor_text) if part
        )
        return (
            "你是资深商业战略顾问，撰写一份有推导深度的品牌商业分析报告 Markdown。\n"
            "\n【核心要求：推导逻辑，不是信息堆砌】\n"
            "每个维度按「事实/数据 → 归因 → 推导链条 → 结论判断」展开，"
            "显式写出推导链条（因为…所以…因此…）；"
            "前一维度的结论必须作为下一维度的输入，环环相扣：\n"
            "用户痛点 → 价值主张；成本结构 → 数字化降本路径；"
            "私域/联名动作 → 营销效果数据 → 增长策略取舍；壁垒评估 → 护城河判断。\n"
            "\n【必须完整覆盖的四大维度】\n"
            "1. 价值主张：先做目标用户画像与痛点剖析（按严重程度排序），"
            "再从痛点推导本品牌为谁、解决什么问题、凭什么优于替代方案；"
            "用对比表格呈现「用户痛点 → 现有方案缺陷 → 本品牌主张」。\n"
            "2. 数字化成本结构：拆解成本大头（获客/履约/人工/库存/营销等），"
            "给出数字化降本路径（自动化工具、私域复购摊薄获客成本、数据驱动选品等），"
            "每条路径注明预期降本幅度与实现前提；"
            "用对比表格呈现「成本项 → 现状 → 数字化后 → 降幅」。\n"
            "3. 私域联名增长策略：私域打法按引流-留存-转化-复购链路展开，"
            "联名策略说明选谁联名、交换什么资源、成本如何分摊；"
            "用数据评估私域营销效果：私域用户占比、复购率、客单价、CAC/LTV、联名活动 ROI，"
            "用表格对比策略上线前后的核心指标变化，并据此说明策略取舍。\n"
            "4. 品牌竞争壁垒：从供应链、渠道、数据资产、用户心智、切换成本等维度评估护城河，"
            "明确判断哪些壁垒真实成立、哪些易被对手复制，并给出加固建议。\n"
            "\n【必出的数据产物】\n"
            "- 行业对标表格：本品牌 vs 主要对标品牌，维度至少含定价、核心渠道、"
            "获客成本、复购率、内容/私域运营打法、差异化优势；\n"
            "- 品牌经营核心数据表：营收/GMV、毛利率、复购率、获客成本、LTV、"
            "私域用户占比等核心指标，其中最关键的 3-4 个建议用大数字指标模块（hero-stat）呈现。\n"
            "\n【数据规范】\n"
            "不得编造无依据的精确数据：公开可查的数据注明来源；"
            "无公开数据时用行业合理区间并标注「行业估算」，或改用定性判断；"
            "严禁输出“待补充”等占位词。\n"
            + (f"\n分析对象：{subject}\n" if subject else "")
            + MODULE_GUIDE
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "商业分析报告"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {
                    "title": "执行摘要",
                    "key_points": ["核心判断", "关键数据速览", "结论预告"],
                },
                {
                    "title": "行业对标与经营现状",
                    "key_points": ["行业对标表格", "品牌经营核心数据", "竞争格局"],
                },
                {
                    "title": "用户痛点剖析",
                    "key_points": ["目标用户画像", "核心痛点排序", "现有方案缺陷"],
                },
                {
                    "title": "价值主张",
                    "key_points": ["痛点到主张的推导", "差异化卖点", "验证依据"],
                },
                {
                    "title": "数字化成本结构与降本路径",
                    "key_points": ["成本结构拆解", "数字化降本路径", "预期降幅与前提"],
                },
                {
                    "title": "私域联名增长策略与效果",
                    "key_points": ["私域运营打法", "联名合作策略", "效果数据与 ROI"],
                },
                {
                    "title": "品牌竞争壁垒与护城河",
                    "key_points": ["壁垒维度评估", "可复制性判断", "加固建议"],
                },
                {
                    "title": "结论与行动建议",
                    "key_points": ["推导链条回顾", "优先级排序", "下一步动作"],
                },
            ],
            meta={"recipe": self.name},
        )


class TravelRecipe(PDFRecipe):
    name = "travel"
    display_name = "旅行手册"
    content_format = "html"
    css_template = "travel"
    color_scheme = "teal"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "攻略标题", "destination": "目的地", "days": 12, '
        '"duration": "12天11晚", "travelers": 2, "countries": "中国 × 哈萨克斯坦", '
        '"tags": ["本地生活", "丝绸之路", "山地自然"], '
        '"route": ["阿拉木图", "希瓦", "布哈拉", "塔什干", "撒马尔罕"], '
        '"summary": "100-150字路线概述", '
        '"watermark": "2-6字目的地简称（如“英伦”“云南”，封面水印用）", '
        '"sections": [{"title": "Day 1", "key_points": ["行程", "美食", "交通"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        theme = str(meta.get("theme") or "travel")
        skeleton, skeleton_name = _load_skeleton(
            theme,
            "travel_optimized.html"
            if theme == "travel_mag"
            else "travel_template.html",
        )
        # 结构化旅行主题（mag/swiss/bento/aurora）共用 day-cards + photo-placeholder
        # + layers/todo-list 富内容契约；经典 travel 用 day-section 紧凑契约
        rich_theme = theme != "travel"
        modern_theme = theme in ("travel_swiss", "travel_bento", "travel_aurora")
        if modern_theme:
            return (
                _skeleton_prompt(
                    "旅行手册作者", "现代风格旅行攻略", skeleton, skeleton_name
                )
                + "1. 只输出 HTML body：以 `<div class=\"page\">` 开头的一串页面片段，"
                "不要输出 ```html 围栏，不要包含 <html>、<head>、<style>、<body>、"
                "<div class=\"page-footer\">，也不要输出解释文字。\n"
                "2. 封面由系统自动生成（标题、导语、标签、行程数据卡来自元信息），"
                "你不要输出封面页。\n"
                "3. 页面顺序固定：路线总览 → 每日行程（每天一个独立 <div class=\"page\">，"
                "同构重复）→ 预算与行前准备。总页数 = 2 + 天数，一页都不要漏。\n"
                "4. 路线总览页：page-head（page-title 内含 <span class=\"lt\"> 高亮字、"
                "meta 短语）→ card「路线走向」内 .stepper：站点依次 .step（.s-dot 序号、"
                ".s-name 城市、.s-stay 停留天数），站点间放 .s-line，末站 class=\"step end\" → "
                "card「每日速览」内 .row-list：每天一个 .row-item（ri-day=D{n}、ri-main=当日主线、"
                "ri-note=住宿、ri-tag=城际交通）→ .info-grid 内单个 .ig-row 并排两个 .card（table-cell 等高）："
                "「节奏说明」（.body-text + .chip-row 内 2-3 个 .chip）与「住宿建议」（check-list）。\n"
                "5. 每日行程页：.day-bar（.day-pill 内 .dp-n=D{n} 与 .dp-d=DAY、.db-main 内 "
                ".db-title=当日主题 与 .db-route=城市及交通方式、.db-chips 可选 1-2 个 .chip）→ "
                ".day-bar 之后、.tl-card 之前输出当日景点图 .photo-grid（class 按当日图片数量取 "
                "p1/p2/p3/p4，与模板 CSS 一致，禁止写成 photos-N）：p1 通栏单图、p2 两张并排、"
                "p4 四宫格，p3 为左 1 右 2——左侧一个大 .ph，右侧用 .ph-side 包两个小 .ph；"
                "每张图一个 .ph，内含 "
                "<span class=\"ph-cap\">景点名 · 看点</span>；用户要求配图时在 .ph 内再放 "
                "<img src=\"keyword:景点名\">（景点名用具体地标或景观的名称，2-6 字，如 \"喀纳斯湖\"、"
                "\"禾木村\"；系统会按关键词搜索真实图片并内嵌，搜不到自动保留渐变占位；"
                "不要自己编造图片 URL，骨架示例中的 picsum 地址必须替换为 keyword: 写法；"
                "不凑数，有几张放几张）→ "
                ".tl-card 内 3 个 .tl-item（tl-time=上午/下午/晚上、tl-title=事项、"
                "tl-body 内 p 一句话 ≤40 字；晚间的 li 用 class=\"tl-item evening\"）→ "
                ".info-grid 内两个 .ig-row，每行并排两个 .info-card（table-cell 等高，.ic-label 分别为：吃什么(卡片加 class food)、"
                "交通与预订、备选方案(加 class alt)、今日提醒(加 class tip)）。\n"
                "6. 预算与行前准备页：page-head → .info-grid 单个 .ig-row 并排两卡："
                "左 .budget-big（.bb-num=总预算、.bb-cap=估算口径），右 .budget-bars"
                "（每个类目一个 .bar-row：.br-top 左名称右 "
                ".amt=\"金额 · 百分比\"、.bar-track 内 .bar-fill style=\"width:百分比%\"，"
                "第 2-5 个 bar-fill 依次加 b2/b3/b4/b5）→ .grid-table-card 内 .mini-table "
                "3-5 行（cat=类目、amt=金额、note=说明）→ .info-grid 两个 .ig-row，每行并排两个 .info-card："
                "行李与天气(check-list)、关键风险(check-list 且 ul 的 class=\"check-list risk\")、"
                "实用链接(link-list：.ln 名称 / .lv 地址)、紧急信息(link-list)。\n"
                "7. 只使用骨架中出现过的 CSS 类名，不要自创类名；时间/价格/班次标注\"以官方为准\"；"
                "内容精炼，宁可每页短也不要漏页。\n"
                f"目的地：{meta.get('destination', intent.topic)}，"
                f"天数：{meta.get('days', '未指定')}，"
                f"路线：{meta.get('route', '未指定')}，"
                f"风格：{meta.get('style', '现代旅行')}"
            )
        return (
            _skeleton_prompt(
                "旅行手册作者", "完整旅行攻略", skeleton, skeleton_name
            )
            + "1. 只输出 HTML body：以 `<div class=\"page\">` 开头的一串页面片段，"
            "不要输出 ```html 围栏，不要包含 <html>、<head>、<style>、<body>、"
            "<div class=\"page-footer\">，也不要输出解释文字。\n"
            "2. 封面由系统自动生成（国家×国家、标题、主题标签、日期、路线概述来自元信息），"
            "你不要输出封面页。\n"
            "3. 页面顺序：路线总览 → 每日行程 → 预算与预订 → 行李、天气与风险控制 → 其他扩展页。"
            "预算页（budget-table/booking-step/payment-note）默认必输出，除非用户明确不要；"
            "行李、天气与风险控制页默认必输出；"
            "用户明确要求某类扩展页（预算/特殊体验/城市读本/实用链接）时，必须输出对应页面，"
            "禁止因“可选”而省略：用户提到预算/花费/费用/省钱 → 预算页；"
            "用户提到行李/天气/风险/安全/清单 → 行李天气与风险控制页；"
            "用户提到特殊体验/深度体验/游牧文化/美食专题 → 对应体验专页。\n"
            "4. 每日行程：每天一个独立的 `<div class=\"page\">`（不要合并两天、"
            "不要用 day-block 类）。每天必须包含：`<h2 class=\"day-title\">` 标题、"
            "`<p class=\"day-subtitle\">` （subtitle-key/subtitle-rest）、"
            "`<table class=\"time-table\">` 的 time-label/time-content 写早上/下午/晚上"
            "（可加上午/中午/傍晚/夜晚），以及三个信息块：吃什么、交通与预订、替代方案"
            + (
                "，用 `<div class=\"day-cards\">` 里的三个 `<div class=\"day-card\">`"
                "（day-card-title/day-card-text）。每张卡片文字控制在 1-2 句、"
                "40 字以内，务必精炼。\n"
                if rich_theme
                else "，用三个 `<div class=\"day-section\">`（day-section-title/day-section-text）。\n"
            )
            + (
                "4.0 每天必须输出一个 `<div class=\"photo-placeholder\">`（放在 day-title 之后），"
                "内含 `<span class=\"photo-note\">当日代表景点 · 看点</span>`，"
                "不要省略这个区块。\n"
                if rich_theme
                else ""
            )
            + "4.1 全程内容必须精简紧凑：每日 time-table 每个时段只写 1 句话（40 字内），"
            "每日整页控制在紧凑篇幅；总原则是输出必须完整覆盖所有规定页面（"
            "路线总览、每天行程、预算、行李天气风险），宁可每页内容精炼，"
            "也不要因内容过长而漏掉后续页面。\n"
            + "5. 行李、天气与风险控制页用 check-list + risk-table（risk-situation/risk-action）"
            "+ highlight-box"
            + (
                "；分层穿衣用 `<div class=\"layers\">` 的 layer-card（layer-no/layer-name/layer-desc），"
                "核对清单用 `<ul class=\"todo-list\">`。\n"
                if rich_theme
                else "；分层穿衣和核对清单用 check-list。\n"
            )
            + "6. 如需扩展板块（专题页/城市读本/预算/链接），使用模板 CSS 中已有的类名："
            "feature-title/feature-subtitle/milestone、city-title/city-tagline/sight/"
            "sight-name/sight-desc、budget-table/booking-step/payment-note、"
            "links-group/links-list/disclaimer。\n"
            "7. 只使用骨架中出现过或规则 6 列出的 CSS 类名，不要自创类名"
            "（尤其不要用 feature-header、feature-section、arrow 等模板里没有的类）。\n"
            "8. 正文纵向堆叠，不用卡片网格；传说与史实分开表述；修复后的外观不等同原貌；"
            "所有时间、价格和班次标注“以官方为准”。\n"
            "9. 封面水印 hero-watermark（封面大图上的超大字背景文字）："
            "按真实情况填 2-6 个字符的目的地简称（如“斯里兰卡”“英伦”“云南”），"
            "不要填完整标题、不要填“{{旅行手册标题简称}}”占位符。\n"
            "10. photo-placeholder 默认只放 photo-note 文字（系统用渐变占位），不要主动放 <img>；"
            "只有用户明确要求配图（或你收到 images=true 提示）时才放 "
            "`<img src=\"图片URL\">`（支持任意图片来源：Unsplash/Pexels/自建图床/用户给的地址），"
            "系统会自动下载内嵌、失败自动保留渐变占位。\n"
            f"目的地：{meta.get('destination', intent.topic)}，"
            f"天数：{meta.get('days', '未指定')}，"
            f"路线：{meta.get('route', '未指定')}，"
            f"风格：{meta.get('style', '深度旅行')}"
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "旅游攻略"
        day_count = 5
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {
                    "title": "路线总览",
                    "key_points": ["逐日行程摘要", "路线逻辑", "住宿区域建议"],
                },
                *[
                    {
                        "title": f"D{index} · 第 {index} 天",
                        "key_points": ["早上", "下午", "晚上", "吃什么", "交通与预订", "替代方案"],
                    }
                    for index in range(1, day_count + 1)
                ],
                {
                    "title": "城市读本",
                    "key_points": ["城市背景", "值得慢看的地方", "现场细节", "观看顺序"],
                },
                {
                    "title": "预算与预订节奏",
                    "key_points": ["预算表", "什么时候订", "付款策略"],
                },
                {
                    "title": "行李天气与风险控制",
                    "key_points": ["分层穿衣", "关键风险", "核对清单"],
                },
                {
                    "title": "实用链接与资料来源",
                    "key_points": ["交通与预订", "历史与目的地背景", "免责声明"],
                },
            ],
            meta={
                "recipe": self.name,
                "destination": "",
                "days": day_count,
                "duration": f"{day_count}天{day_count - 1}晚",
                "travelers": "",
                "countries": "",
                "tags": [],
                "route": [],
                "summary": "",
                "style": "深度旅行",
            },
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        esc = html_lib.escape
        destination = esc(str(meta.get("destination") or intent.topic))
        try:
            day_count = int(meta.get("days") or 5)
        except (TypeError, ValueError):
            day_count = 5
        route = meta.get("route") or []
        route_items = (
            [esc(str(item)) for item in route if str(item).strip()]
            if isinstance(route, list)
            else []
        )
        route_cities = ""
        for index, city in enumerate(route_items):
            if index:
                route_cities += '<span class="arrow">→</span>'
            route_cities += f"<span>{city}</span>"
        countries = esc(str(meta.get("countries") or ""))
        duration = esc(
            str(meta.get("duration") or f"{day_count}天{day_count - 1}晚")
        )
        route_stops = "".join(
            f'<div class="route-stop {"above" if index % 2 == 0 else "below"}">'
            f'<span class="stop-name">{city}</span></div>'
            for index, city in enumerate(route_items)
        )
        route_map_block = (
            f'<div class="route-map"><div class="route-stops">{route_stops}</div></div>'
            if route_items
            else ""
        )

        pages = [
            f"""<div class="page">
  <h2 class="section-title">路线总览</h2>
  <p class="section-subtitle">{duration}｜{countries}｜尽量全程陆路</p>
  {route_map_block}
  <p class="route-meta">{route_cities}｜全程信息以官方为准</p>
  <table class="route-table">
    <thead>
      <tr>
        <th>日期</th>
        <th>地点与主题</th>
        <th>主要交通</th>
        <th>住宿</th>
      </tr>
    </thead>
    <tbody>"""
        ]
        for index in range(1, day_count + 1):
            pages.append(
                f"""      <tr>
        <td>D{index}</td>
        <td>{destination}：当日主题</td>
        <td>待确认</td>
        <td>待确认</td>
      </tr>"""
            )
        pages.append(
            """    </tbody>
  </table>
  <div class="highlight-box">
    <div class="box-title">路线逻辑</div>
    <ul class="check-list">
      <li><strong>自然：</strong>沿途地理与气候主线。</li>
      <li><strong>历史：</strong>丝路城市的历史层次。</li>
      <li><strong>文化：</strong>当地生活与少数族群观察。</li>
      <li><strong>节奏：</strong>每天保留替代方案，避免被天气或班次打乱。</li>
    </ul>
  </div>
  <h3 class="subsection-title">住宿区域建议</h3>
  <ul class="check-list">
    <li><strong>各城市：</strong>优先住在步行可达旧城或车站的区域，预留班次波动缓冲。</li>
  </ul>
</div>"""
        )

        for index in range(1, day_count + 1):
            pages.append(
                f"""<div class="page">
  <h2 class="day-title">D{index}｜第 {index} 天</h2>
  <p class="day-subtitle"><span class="subtitle-key">当日核心目标</span></p>
  <table class="time-table">
    <tr><td class="time-label">早上</td><td class="time-content">抵达或出发后的第一段安排。</td></tr>
    <tr><td class="time-label">下午</td><td class="time-content">当天的核心游览与交通衔接。</td></tr>
    <tr><td class="time-label">晚上</td><td class="time-content">住宿、晚餐与第二天准备。</td></tr>
  </table>
  <div class="day-section"><div class="day-section-title">吃什么</div><div class="day-section-text">当地特色餐食与点餐建议。</div></div>
  <div class="day-section"><div class="day-section-title">交通与预订</div><div class="day-section-text">车次/门票/入住时间，以官方为准。</div></div>
  <div class="day-section"><div class="day-section-title">替代方案</div><div class="day-section-text">天气或班次变化时删什么、保什么、移到哪里。</div></div>
</div>"""
            )

        pages.append(closing_pages_html())
        return "\n".join(pages).strip()


class PageTemplateRecipe(PDFRecipe):
    """页式 HTML 模板配方基类（论文/报告四套）。

    与 TravelRecipe 同一管线：LLM 按模板骨架输出 HTML body，模板自带封面页
    与页眉页脚（theme_registry 的 own_cover 标记），系统不再另造封面。

    子类只需给出 html_theme 与两段提示词增量：
    - page_plan：固定页面顺序与每页必出要素（防漏页、防改序）
    - extra_rules：该模板特有的排版契约（图表编号、公式编号、刻度对齐等）
    """

    content_format = "html"
    html_theme = ""
    color_scheme = "blue"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    page_plan = ""
    extra_rules = ""

    @property
    def expected_pages(self) -> int:
        """模板的固定页数（取自 pdf_themes 模板的页片段数）。"""
        from .theme_manager import html_template_pages

        return len(html_template_pages(self.html_theme))

    def content_system_prompt(self, intent: PDFIntent) -> str:
        skeleton, skeleton_name = _load_skeleton(self.html_theme)
        return (
            _skeleton_prompt(
                f"{self.display_name}撰稿人", "", skeleton, skeleton_name
            )
            + "1. 只输出 HTML body：以 `<div class=\"page\">` 开头的一串页面片段。"
            "不要输出 ```html 围栏，不要包含 <html>、<head>、<style>、<body>，"
            "也不要输出任何解释文字。\n"
            "2. 页面顺序与页数必须与骨架完全一致，一页都不能少、不能合并、不能加页；"
            "封面页也要输出（骨架里第一段 `<div class=\"page cover\">`）。\n"
            "3. 骨架里所有 {{占位符}} 必须替换为真实内容，输出中不得残留 {{ 或 }}。\n"
            "4. 只使用骨架中出现过的 CSS 类名与标签嵌套，不要自创类名、不要改动 class 名、"
            "不要给元素加行内 style（骨架里已有的 width 百分比除外）。\n"
            "5. 数据必须自洽：表内合计 = 各行之和，百分比与绝对量对得上，"
            "正文引用的数字与表格一致。\n"
            "6. 不得编造无依据的精确数据：公开可查的注明来源；无来源时用行业合理区间并"
            "标注「行业估算」；严禁输出「待补充」「XX」等占位词。\n"
            + (self.page_plan + "\n" if self.page_plan else "")
            + (self.extra_rules + "\n" if self.extra_rules else "")
            + f"\n文档主题：{intent.topic}\n标题：{intent.title}"
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        """无 LLM 时的降级内容：取模板自身的页片段，把 {{占位符}} 去掉花括号当示例文案。

        只取 `<div class="page">` 片段，不取头部注释——注释是给人看的设计说明，
        当正文输出会变成可见文字。
        """
        from .theme_manager import html_template_pages

        pages = html_template_pages(self.html_theme)
        body = "\n".join(pages)
        return re.sub(r"\{\{(.*?)\}\}", r"\1", body, flags=re.DOTALL).strip()


class AcademicReportRecipe(PageTemplateRecipe):
    name = "academic_report"
    display_name = "学术报告"
    html_theme = "academic_report"
    css_template = "academic_report"
    color_scheme = "blue"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "研究主题", '
        '"institution": "大学/研究机构名称", "department": "学院·系/研究中心", '
        '"author": "作者姓名", "student_id": "学号", "advisor": "导师姓名", "degree": "职称", '
        '"date": "2026 年 9 月", "course_no": "课程编号", "term": "2026 秋季学期", '
        '"keywords": ["关键词一", "关键词二", "关键词三"], '
        '"sections": [{"title": "1 绪论", "key_points": ["研究背景", "国内外现状"]}]}'
    )
    page_plan = (
        "【页面顺序（4 页，不可增减）】\n"
        "P1 封面：机构名 / 院系 / 报告类型 / 标题 / 副标题 / 作者信息表（作者·学号、导师、院系、日期）/ 页脚课程编号。\n"
        "P2 摘要·关键词·目录：摘要框（一段 150-220 字，含研究问题、方法、核心指标结果）、"
        "4 个关键词胶囊、目录（一级 + 二级条目，页码按正文实际页序填 03/03/04/04）。\n"
        "P3 正文前半：`1 绪论`（含 1.1 研究背景与意义、1.2 国内外研究现状）、"
        "`2 相关理论与方法`（含 2.1 小节），并输出 `图 2-1` 的图位块。\n"
        "P4 正文后半：`3 实验设计与结果分析`（含表 3-1 三线表）、`4 结论与展望`（①②③ 三条）、"
        "`参考文献`（4 条，[1]-[4] 格式）。\n"
        "P2 目录里的条目必须与 P3/P4 实际出现的章节标题逐字一致。"
    )
    extra_rules = (
        "【本模板排版契约】\n"
        "- 章节标题用 `<h2 class=\"sec-h1\"><span class=\"no\">编号</span>标题</h2>`；"
        "二级用 `<h3 class=\"sec-h2\"><span class=\"no\">1.1</span>标题</h3>`；"
        "无编号章节（摘要/目录/参考文献）的 `<span class=\"no\">` 填 `§`。\n"
        "- 正文段落必须用 `<p class=\"body-text\">`，首段不要额外加缩进类。\n"
        "- 图用 `<div class=\"fig-block\">`：内层 `<div class=\"fig-placeholder\">` 写图位说明，"
        "下方 `<div class=\"fig-caption\"><span class=\"fg-no\">图 2-1</span>图题</div>`；**图题在图下方**。\n"
        "- 表用 `<div class=\"tb-caption\"><span class=\"tb-no\">表 3-1</span>表题</div>` 放在 `<table class=\"three-line-table\">` **之前**；"
        "数值列 `<th>`/`<td>` 加 `class=\"num\"` 右对齐；最优行用 `<strong>` 加粗。\n"
        "- 结论三条用 `<div class=\"concl-item\"><div class=\"no\">①</div><div class=\"txt\">…</div></div>`。\n"
        "- 参考文献用 `<div class=\"ref-item\"><span class=\"ref-no\">[1]</span> 条目</div>`，按 GB/T 7714 格式。"
    )


class ThesisPaperRecipe(PageTemplateRecipe):
    name = "thesis_paper"
    display_name = "论文投稿"
    html_theme = "thesis_paper"
    css_template = "thesis_paper"
    color_scheme = "monochrome"
    intent_json_hint = (
        '{"title": "论文标题", "title_en": "English Title", "topic": "研究主题", '
        '"clc": "中图分类号", "doc_code": "文献标志码", "received": "收稿日期", '
        '"authors": ["第一作者", "第二作者"], "affiliations": ["单位一，城市 邮编"], '
        '"journal": "期刊名/学报名称", "issue": "卷期号", '
        '"keywords": ["关键词一", "关键词二"], '
        '"sections": [{"title": "1 相关理论与问题定义", "key_points": ["形式化定义", "公式"]}]}'
    )
    page_plan = (
        "【页面顺序（3 页，不可增减）】\n"
        "P1 标题区 + 摘要 + 引言：中图分类号行 → 中文大标题 → 英文标题 → 作者与单位 → "
        "摘要块（摘要正文 + 关键词行）→ `0 引言`（两段）。\n"
        "P2 方法与实验：`1 相关理论与问题定义`（含一条居中公式与式中说明）、"
        "`2 所提方法`（含 `图 1` 图位）、`3 实验与结果分析`（含 `3.1 实验设置与对比结果` 与 `表 1` 三线表 + 表注）。\n"
        "P3 消融与结论：以续排眉题 `<div class=\"sec-cont\">3　实验与结果分析（续）</div>` 开头 → "
        "`3.2 消融实验`（含 `表 2`）→ `4 结论` → `致谢` → `参考文献`（5 条，[1]-[5]）。\n"
        "P2 必须出现 `3.1`，P3 才接 `3.2`，编号不能跳号。"
    )
    extra_rules = (
        "【本模板排版契约】\n"
        "- 章节标题用 `<h2 class=\"sec-h1\">3　实验与结果分析</h2>`（编号与标题之间用全角空格）；"
        "二级用 `<h3 class=\"sec-h2\">3.1　实验设置与对比结果</h3>`。\n"
        "- 正文段落必须用 `<p class=\"body-text\">`；紧跟表格的说明段加 `no-indent` 类。\n"
        "- 公式用 `<div class=\"eq-row\"><div class=\"eq\">公式</div><div class=\"eq-no\">(1)</div></div>`，"
        "编号按出现顺序 (1)(2)…；上下标用 `<sub>`。\n"
        "- 三线表：`<div class=\"tb-title\">表 1　表题</div>` 在 `<table class=\"table3\">` 之前；"
        "**表注必须写成 `<div class=\"tbl-note\">注：…</div>` 放在 `</table>` 之后**，"
        "绝不能作为 `<tr>` 放进表格内（会让三线表收尾粗线错位）。\n"
        "- 图用 `<div class=\"fig-frame\">图位说明</div>` + `<div class=\"fig-title\">图 1　图题</div>`（图题在图下方）。\n"
        "- 参考文献用 `<div class=\"ref-item\"><span class=\"no\">[1]</span> 条目</div>`。"
    )


class DataReportRecipe(PageTemplateRecipe):
    name = "data_report"
    display_name = "数据分析报告"
    html_theme = "data_report"
    css_template = "data_report"
    color_scheme = "blue"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "分析对象与期间", '
        '"org": "数据团队/部门名称", "quarter": "2026-Q3", "business": "业务线", '
        '"period": "2026.07 – 2026.09", "kpis": ['
        '{"value": "1,284", "unit": "万", "label": "月活跃用户", "delta": "▲ 同比 +12.6%", "trend": "up"}], '
        '"regions": ["华东", "华南", "华北", "西南"], '
        '"sections": [{"title": "核心指标概览", "key_points": ["分渠道营收", "费用结构"]}]}'
    )
    page_plan = (
        "【页面顺序（4 页，不可增减）】\n"
        "P1 封面：机构名 + 报告类型 + 业务线标签 + 大标题 + 分析区间 + 摘要块 + "
        "**四栏 KPI 指标带**（数值/单位/指标名/涨跌）+ 底部深色收底带（分析周期、数据来源、出品）。\n"
        "P2 核心指标概览：章节头 `01` → 四栏 KPI 带 → 概述段 → "
        "`分渠道营收结构`（4 条条形图 + 刻度轴 + 图注）→ `费用与成本结构`（3 条条形图 + 刻度轴 + 图注）。\n"
        "P3 明细数据与关键洞察：章节头 `02` → `分区域经营明细` 表（4 个区域 + 1 行合计）+ 表注 → "
        "`关键洞察` 4 条（洞察 1…洞察 4）。\n"
        "P4 结论与行动建议：章节头 `03` → `核心结论` ①②③ → `行动建议` 表（4 行）→ 表注 → "
        "`口径与附注` 3 条。"
    )
    extra_rules = (
        "【本模板排版契约（图表刻度对齐是关键）】\n"
        "- 章节头用骨架里的 `<div class=\"sec-head\">` 三行结构（sec-no / sec-title / sec-en），"
        "编号依次 `01` `02` `03`。\n"
        "- KPI 一栏 = `<div class=\"kc\"><div class=\"kv\">数值<em>单位</em></div>"
        "<div class=\"kk\">指标名</div><div class=\"kd up|down\">▲/▼ 变化</div></div>`；"
        "涨用 `kd up` + `▲`，跌用 `kd down` + `▼`。封面与 P2 各出现一次，两处数值必须一致。\n"
        "- **条形图刻度必须与条长对齐**：`.chart-plot` 内容宽度代表 100%，"
        "所以 `style=\"width: N%\"` 的 N 就是该项占最大值的比例；"
        "`.chart-axis` 的 4 个 `<span>` 必须等分且依次为 `0`（左对齐）、"
        "`<span style=\"text-align: left;\">25% 刻度值</span>`、"
        "`<span style=\"text-align: left;\">50% 刻度值</span>`、"
        "`<span style=\"text-align: right;\">100% 刻度值</span>`；"
        "**中间两格必须用 `text-align: left`，写成 center 会让刻度右偏到 37.5%/62.5%**。\n"
        "- 条形图每条：`<div class=\"chart-row\"><div class=\"cr-top\"><span class=\"l\">名称</span>"
        "<span class=\"v\">数值 · 占比</span></div><div class=\"chart-bar\" style=\"width: N%;\"></div></div>`；"
        "第 2/3/4 条的 `chart-bar` 依次加 `c2`/`c3`/`c4` 类。\n"
        "- 数据表用 `<table class=\"fin-table\">`；数值单元格加 `class=\"num\"`；"
        "合计行 `<tr class=\"total\">`；正增长 `class=\"num pos\"`、负增长 `class=\"num neg\"`。"
        "「优先级 / 时限」这类文本列**不要**加 `num`（表头是左对齐的）。\n"
        "- 表注统一用 `<div class=\"tbl-note\">注：…</div>` 放在表格之后。\n"
        "- 洞察用 `<div class=\"insight-item\"><div class=\"i-no\">洞察 1</div>"
        "<div class=\"i-body\"><div class=\"i-title\">标题</div><p>正文</p></div></div>`，编号固定「洞察 1..4」。"
    )


class ResearchReportRecipe(PageTemplateRecipe):
    name = "research_report"
    display_name = "研究报告"
    html_theme = "research_report"
    css_template = "research_report"
    color_scheme = "green"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "研究主题与行业", '
        '"org": "研究机构/咨询团队", "ref_no": "RR-2026-041", '
        '"publish_date": "2026 年 9 月", "research_period": "2024.01 – 2026.09", '
        '"owner": "姓名 · 职务", "confidential": "内部资料 · 请勿外传", '
        '"agenda": ["执行摘要与关键发现", "市场格局", "战略路径与行动建议"], '
        '"sections": [{"title": "市场格局", "key_points": ["供给端", "需求端", "政策"]}]}'
    )
    page_plan = (
        "【页面顺序（4 页，不可增减）】\n"
        "P1 封面：机构名 + REF 编号 + 报告类型 + 衬线大标题 + 副标题 + 摘要段 + "
        "**底部目录**（3 条 agenda）+ 深色收底带（发布日期、研究周期、项目负责人、密级）。\n"
        "P2 执行摘要·关键发现：页眉条（`Executive Summary · 执行摘要` + 报告标题）→ `Section 01` + `执行摘要` 标题 → "
        "引用块（一句话核心判断）→ `关键发现` 3 条（01/02/03，每条含标题、正文、一个数据胶囊）。\n"
        "P3 深度分析：页眉条（`Analysis · 深度分析`）→ `Section 02` + 章节标题 + 章节导语 → "
        "两个 `duo` 双栏面板组（供给端/需求端、市场规模测算/政策与监管变量）→ 图表框 + 图题。\n"
        "P4 战略建议·风险·尾注：页眉条（`Strategy · 战略建议`）→ `Section 03` + 章节标题 + 章节导语 → "
        "建议矩阵表（3 行，含优先级胶囊）→ `风险提示` 表（3 行）→ 尾注段。"
    )
    extra_rules = (
        "【本模板排版契约】\n"
        "- 每页（P2-P4）第一行必须是页眉条 `<div class=\"page-head\">"
        "<span class=\"ph-l\">英文眉题 · 中文眉题</span><span class=\"ph-r\">报告标题</span></div>`；"
        "P1 封面不要页眉条。\n"
        "- 章节眉题用 `<div class=\"sec-kicker\">Section 0N</div>`，编号 01/02/03。\n"
        "- 关键发现用 `<div class=\"finding\"><div class=\"f-no\">01</div><div class=\"f-body\">"
        "<div class=\"f-title\">标题</div><p>正文</p><span class=\"f-data\">指标 · 数值</span></div></div>`。\n"
        "- 双栏面板用 `<div class=\"duo\"><div class=\"panel\">…</div><div class=\"duo-gap\"></div>"
        "<div class=\"panel\">…</div></div>`；面板内小标题 `p-title`，要点列表 `ul.p-list` 下每项一个 `<li>`。\n"
        "- 建议矩阵 `<table class=\"matrix\">`：列宽用骨架里的 `style=\"width: …%\"` 原样保留；"
        "优先级胶囊 `<span class=\"badge p0\">P0 · 立即启动</span>`（P1 用 `p1`、P2 用 `p2`）。\n"
        "- 风险表 `<table class=\"risk-table\">`，风险项单元格加 `class=\"rk\"`。\n"
        "- 尾注用 `<div class=\"endnote\">尾注：…</div>`。"
    )


class QuotesSketchRecipe(PageTemplateRecipe):
    """金句手绘解读：一卡一页的金句卡组（封面 + 6 张卡 + 尾页 = 8 页）。

    与论文/报告四套同一管线，但版式意图相反——那四套是「信息密度优先」，
    这一套是「留白优先」：每页只有一条金句 + 一段解读，整页垂直居中。
    因此本配方对字数上限的要求比其他配方严格得多（超字数会溢出到第二页）。
    """

    name = "quotes_sketch"
    display_name = "金句手绘解读"
    html_theme = "quotes_sketch"
    css_template = "quotes_sketch"
    color_scheme = "monochrome"
    intent_json_hint = (
        '{"title": "金句集标题", "topic": "材料主题", '
        '"series": "系列标签（4–6 字）", "subtitle": "副标题（8–16 字）", '
        '"source": "时间与出处（12–24 字）", "preface": "卷首语（40–80 字）", '
        '"quotes": [{"label": "小标题（4–6 字）", "quote": "金句原文（20–40 字）", '
        '"note": "解读（50–90 字）", "art": "配图说明（8–16 字）"}], '
        '"closing": "结语（6–12 字）", "colophon": "版权与说明（16–32 字）"}'
    )
    page_plan = (
        "【页面顺序（8 页，不可增减）】\n"
        "P1 封面：系列标签 → 主标题 → 副标题 → 时间与出处 → 卷首语 → 分隔短线。\n"
        "P2 金句卡 01（带插图位）：虚线插图位（图注一句）→ 眉标 `N° 01 · 小标题` → "
        "金句原文 → 解读。\n"
        "P3 金句卡 02（纯文字）：眉标 → 引号饰件 → 金句原文 → 解读。\n"
        "P4 金句卡 03（纯文字）：结构同 P3。\n"
        "P5 金句卡 04（带插图位）：结构同 P2。\n"
        "P6 金句卡 05（纯文字）：结构同 P3。\n"
        "P7 金句卡 06（纯文字）：结构同 P3。\n"
        "P8 尾页：分隔短线 → 结语 → 版权与说明。\n"
        "六张卡片的 {{序号}} 依次填 01–06；六条金句与六段解读互不重复，"
        "且都取自同一份材料，不要凑数、不要重复同一句话的不同说法。"
    )
    extra_rules = (
        "【本模板排版契约（一卡一页，超字数会挤到第二页）】\n"
        "- 每个 `<div class=\"page\">` 就是一页：不要增页、不要合并卡片、不要改 class 名。\n"
        "- 三种页的类名不能混用：P1 是 `<div class=\"page cover\">`、P2–P7 是 `<div class=\"page\">`、"
        "P8 是 `<div class=\"page end\">`。\n"
        "- 卡片两种形态严格照骨架，不要互换：P2/P5 用 `<article class=\"card card--art\">`"
        "（含 `<figure class=\"frame\">` 与虚线插图位 `<div class=\"plate\">`）；"
        "P3/P4/P6/P7 用 `<article class=\"card card--text\">`"
        "（含引号饰件 `<span class=\"qm\" aria-hidden=\"true\">&ldquo;</span>`）。\n"
        "- 插图位是虚线「图位」，不是真图：`{{配图说明}}` 只写一句图注（8–16 字），"
        "**不要**插入 `<img>`、不要写图片 URL、也不要留空。\n"
        "- 字数上限（超了会溢出到第二页）：{{卷首语}} ≤ 80 字、{{金句原文}} ≤ 40 字、"
        "{{解读}} ≤ 90 字、{{小标题}} ≤ 6 字、{{结语}} ≤ 12 字、{{版权与说明}} ≤ 32 字。\n"
        "- 金句原文是整页的视觉主体，保持一句话：不要把解读并进 `<blockquote>`，"
        "也不要给 `<blockquote>` 加编号或引号。\n"
        "- 只用骨架里出现过的标签与类名，不要自创类名、不要给元素加行内 style。"
    )


PAGE_TEMPLATE_RECIPES: frozenset[str] = frozenset(
    {
        "academic_report",
        "thesis_paper",
        "data_report",
        "research_report",
        "quotes_sketch",
    }
)


class RoadmapRecipe(PDFRecipe):
    name = "roadmap"
    display_name = "学习路线"
    css_template = "modern"
    color_scheme = "blue"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "路线标题", "topic": "学习主题", '
        '"sections": [{"title": "阶段名", "key_points": ["知识点", "资源", "练习"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是技术教育专家。根据学习路线结构生成系统化 Markdown 学习指南。\n"
            "要求：每个阶段一节；节点用卡片格式；资源用列表；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"学习主题：{intent.topic}"
            + MODULE_GUIDE
        )


class BookRecipe(PDFRecipe):
    name = "book"
    display_name = "电子书/手册"
    css_template = "academic"
    color_scheme = "warm"
    intent_json_hint = (
        '{"title": "书名", "topic": "手册主题", '
        '"sections": [{"title": "章标题", "key_points": ["小节", "要点"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是书籍/手册作者。根据章节结构撰写可读性强、结构完整的 Markdown 内容。\n"
            "要求：每章一节；包含引言、正文、小结；不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"主题：{intent.topic}"
            + MODULE_GUIDE
        )


class SlideRecipe(PDFRecipe):
    name = "slide"
    display_name = "讲义"
    css_template = "minimal"
    color_scheme = "monochrome"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": True,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "讲义标题", "topic": "课程主题", '
        '"sections": [{"title": "小节", "key_points": ["要点", "示例"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是课程讲师。根据提纲生成适合打印的讲义 Markdown。\n"
            "要求：每个小节一节；每节先给结论再展开；控制信息密度；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"课程主题：{intent.topic}"
            + MODULE_GUIDE
        )


class ResumeRecipe(PDFRecipe):
    name = "resume"
    display_name = "个人简历"
    css_template = "resume"
    color_scheme = "blue"
    # 简历各区块共用 resume-header 等结构类，必须整篇一次生成
    sectioned_content = False
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "姓名 - 目标职位", "name": "姓名", "role": "目标职位", '
        '"contact": "邮箱 · 电话 · 城市", "summary": "一句话简介", '
        '"skills": ["技能一", "技能二"], '
        '"sections": [{"title": "工作经历", "key_points": ["公司 · 职位 · 时间", "成果一"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        return (
            "你是资深简历顾问。根据简历结构输出适合直接打印的单页 A4 简历 HTML。\n"
            "使用以下类：resume-header、resume-name、resume-role、resume-contact、"
            "resume-summary、resume-section、skill-tag、experience-item、"
            "project-card、resume-point。\n"
            "要求：信息密度高、无多余装饰；不要使用 SVG 插图。\n"
            "内容规范：把职责描述改成成果描述；每条经历保留 2-4 条高密度 bullet；\n"
            "bullet 使用“动作 + 产物 + 结果”结构，优先量化；没有精确数字时写范围、频率或流程变化；\n"
            "严禁编造指标、头衔或项目背景，缺失数据用“[量化数据待补]”占位；\n"
            "每个项目先写一句背景（系统定位 + 服务对象 + 解决什么问题），再列 bullet；\n"
            "Kami 风格时项目按 角色/动作/结果 三段式，impact 必须量化；\n"
            "核心技能按 分类|内容 的技能行组织，内容写 1-2 行并尽量占满整行；\n"
            "工作经历按 公司/部门/角色 + 项目子标题 + 2-4 条成果 bullet；\n"
            "页数按内容实际需要控制，不强制一页；用户要求一页版时再压缩。\n"
            f"姓名：{meta.get('name', intent.title)}，"
            f"目标职位：{meta.get('role', '')}"
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "个人简历"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {"title": "个人简介", "key_points": [user_input]},
                {"title": "核心技能", "key_points": ["技能一", "技能二"]},
                {"title": "工作经历", "key_points": ["公司 · 职位 · 时间"]},
                {"title": "项目经历", "key_points": ["项目名称 · 成果"]},
                {"title": "教育背景", "key_points": ["学校 · 专业 · 时间"]},
            ],
            meta={
                "recipe": self.name,
                "name": user_input,
                "role": "",
                "contact": "",
                "summary": user_input,
                "skills": [],
            },
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        name = html_lib.escape(str(meta.get("name") or intent.title))
        role = html_lib.escape(str(meta.get("role") or ""))
        contact = html_lib.escape(str(meta.get("contact") or ""))
        summary = html_lib.escape(str(meta.get("summary") or intent.topic))
        skills = meta.get("skills") or []

        lines = [
            '<div class="resume-header">',
            f'<div class="resume-name">{name}</div>',
            f'<div class="resume-role">{role}</div>' if role else "",
            f'<div class="resume-contact">{contact}</div>' if contact else "",
            "</div>",
            f'<div class="resume-summary">{summary}</div>',
        ]
        if isinstance(skills, list) and skills:
            tags = "".join(
                f'<span class="skill-tag">{html_lib.escape(str(skill))}</span>'
                for skill in skills
            )
            lines.append('<div class="resume-section-title">核心技能</div>')
            lines.append(f'<div class="skill-tags">{tags}</div>')

        for section in intent.sections:
            title = str(section.get("title") or "经历")
            points = section.get("key_points") or []
            lines.append(f'<div class="resume-section-title">{html_lib.escape(title)}</div>')
            card_class = (
                "experience-item"
                if any(word in title for word in ("工作", "经历"))
                else "project-card"
                if "项目" in title
                else "resume-block"
            )
            lines.append(f'<div class="{card_class}">')
            for point in points:
                lines.append(
                    f'<div class="resume-point">{html_lib.escape(str(point))}</div>'
                )
            lines.append("</div>")
        return "\n".join(line for line in lines if line).strip()


RECIPE_REGISTRY: dict[str, type[PDFRecipe]] = {
    recipe.name: recipe
    for recipe in (
        ReportRecipe,
        BusinessAnalysisRecipe,
        TravelRecipe,
        AcademicReportRecipe,
        ThesisPaperRecipe,
        DataReportRecipe,
        ResearchReportRecipe,
        QuotesSketchRecipe,
        RoadmapRecipe,
        BookRecipe,
        SlideRecipe,
        ResumeRecipe,
    )
}


def get_recipe(name: str | None) -> PDFRecipe:
    key = (name or "").strip().lower()
    cls = RECIPE_REGISTRY.get(key) or ReportRecipe
    return cls()


def detect_recipe(user_input: str) -> str:
    text = user_input.lower()
    if any(
        word in text
        for word in ("简历", "resume", "cv", "求职")
    ):
        return "resume"
    if any(
        word in text
        for word in ("旅游", "攻略", "行程", "旅行", "景点", "目的地")
    ):
        return "travel"
    if any(
        word in text
        for word in ("学习路线", "路线图", "学习路径", "从入门到", "roadmap")
    ):
        return "roadmap"
    # 金句卡组：产物形态非常特定（一卡一页的语录卡），比「论文/报告」这类
    # 题材词更能代表用户想要的成品，故排在论文/报告四套之前——
    # 「把这篇论文的金句做成卡片」要的是卡片，不是论文。
    if any(
        word in text
        for word in (
            "金句", "语录", "名言", "金句卡", "手绘解读", "quote",
        )
    ):
        return "quotes_sketch"
    # 论文/报告四套：比 business/report 更具体的词先判，避免被宽泛词吸走
    if any(
        word in text
        for word in (
            "论文", "学位论文", "期刊论文", "学术论文", "毕业论文", "投稿",
            "会议论文", "thesis", "paper",
        )
    ):
        return "thesis_paper"
    if any(
        word in text
        for word in (
            "学术报告", "课程报告", "结课报告", "开题", "课题", "学术汇报",
            "文献综述", "实验报告",
        )
    ):
        return "academic_report"
    if any(
        word in text
        for word in (
            "数据分析", "数据报告", "经营数据", "指标分析", "经营复盘",
            "数据复盘", "经营分析报告", "季度经营", "经营数据分析",
        )
    ):
        return "data_report"
    if any(
        word in text
        for word in (
            "研究报告", "行业研究", "白皮书", "咨询报告", "战略研究",
            "深度研究", "市场研究", "research report",
        )
    ):
        return "research_report"
    if any(
        word in text
        for word in (
            "商业分析", "商业模式", "商业计划", "商业报告", "经营分析",
            "商业画布", "品牌分析", "品牌战略", "品牌诊断", "品牌定位",
            "竞品", "对标", "护城河", "私域", "联名", "增长策略",
            "business analysis", "business plan",
        )
    ):
        return "business"
    if any(
        word in text
        for word in ("报告", "周报", "月报", "分析", "调研", "总结")
    ):
        return "report"
    if any(
        word in text
        for word in ("电子书", "手册", "书籍", "书", "指南", "book")
    ):
        return "book"
    if any(
        word in text
        for word in ("讲义", "提纲", "幻灯片", "演示", "课程", "讲座")
    ):
        return "slide"
    return "report"
