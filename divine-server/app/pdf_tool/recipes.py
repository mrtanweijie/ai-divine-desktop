from __future__ import annotations

import html as html_lib

from .base import PDFIntent, PDFRecipe


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
        )


class TravelRecipe(PDFRecipe):
    name = "travel"
    display_name = "旅行手册"
    content_format = "html"
    css_template = "travel"
    color_scheme = "warm"
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
        '"route": ["阿拉木图", "希瓦", "布哈拉", "塔什干", "撒马尔罕"], '
        '"summary": "100-150字路线概述", '
        '"sections": [{"title": "Day 1", "key_points": ["行程", "美食", "交通"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        return (
            "你是资深旅行手册作者。根据行程结构输出一份可直接打印为 PDF 的完整旅行攻略 HTML body，"
            "版式 100% 参考旅行手册 HTML 模板：米白纸感、暖橙 + 青蓝、衬线标题。\n"
            "只输出 HTML body 片段：不要输出 ```html 围栏，不要包含 <html>、<head>、<style>、"
            "<body>、页面页脚，也不要输出解释文字；不要自创 class，不要输出 Markdown。\n"
            "必须按以下顺序输出完整结构：\n"
            "1. `<div class=\"page\">` 内写 `路线总览`：天数/晚数/国家数/交通原则，一张逐日行程摘要表，"
            "3-5 条路线逻辑，每个住宿城市的区域建议；\n"
            "2. 每日行程：每个 `<div class=\"page\">` 放一天，跨境日或紧凑日可两天同页但必须用 "
            "`<hr class=\"day-divider\">` 分隔；每天用 `<h2 class=\"day-title\">` + "
            "`<span class=\"day-badge\">D1</span>`，再用 `<div class=\"time-row morning\">`、"
            "`<div class=\"time-row afternoon\">`、`<div class=\"time-row evening\">` 写三段，"
            "最后用 `<div class=\"day-info\">` 写“吃什么/交通与预订/替代方案”三段；\n"
            "3. 专题页（可选 2-4 页）：用 `<div class=\"feature-header\">`、"
            "`<div class=\"feature-section\">`，关键日深读用 `<div class=\"milestone\">` 时间线；\n"
            "4. 城市读本：用 `<div class=\"city-header\">`、`<p class=\"city-intro\">`、"
            "`<div class=\"sight-name\">`、`<div class=\"sight-desc\">`、"
            "`<div class=\"field-notes\">`、`<div class=\"viewing-order\">`；\n"
            "5. 收尾：预算页用 `<table class=\"budget-table\">` + "
            "`<div class=\"booking-timeline-item\">` + `<div class=\"payment-strategy\">`；"
            "行李页用 `<ul class=\"plain-list\">` + `<table class=\"risk-table\">` + "
            "`<div class=\"checklist\">`；链接页用 `<div class=\"links-group\">` + "
            "`<ul class=\"links-list\">` + `<div class=\"disclaimer\">`。\n"
            "排版要求：每个大板块用一个 `<div class=\"page\">`；正文纵向堆叠，不用卡片网格；"
            "传说与史实分开表述；"
            "所有时间、价格和班次标注“以官方为准”；不要输出完整 HTML 文件，"
            "只输出可直接嵌入页面的 HTML body。\n"
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
                "destination": user_input,
                "days": day_count,
                "duration": f"{day_count}天{day_count - 1}晚",
                "travelers": 1,
                "countries": "",
                "route": [],
                "summary": "围绕用户需求生成的一份完整旅行攻略。",
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

        pages = [
            f"""<div class="page">
  <h2 class="section-title">路线总览</h2>
  <p class="section-subtitle">{duration}｜{countries}｜尽量全程陆路</p>
  <div class="route-cities">{route_cities}</div>
  <p class="route-distance">{destination}｜全程信息以官方为准</p>
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
  <h3 class="subsection-title">路线逻辑</h3>
  <ul class="plain-list">
    <li><strong>自然：</strong>沿途地理与气候主线。</li>
    <li><strong>历史：</strong>丝路城市的历史层次。</li>
    <li><strong>文化：</strong>当地生活与少数族群观察。</li>
    <li><strong>节奏：</strong>每天保留替代方案，避免被天气或班次打乱。</li>
  </ul>
  <h3 class="subsection-title">住宿区域建议</h3>
  <ul class="plain-list">
    <li><strong>各城市：</strong>优先住在步行可达旧城或车站的区域，预留班次波动缓冲。</li>
  </ul>
</div>"""
        )

        for index in range(1, day_count + 1):
            pages.append(
                f"""<div class="page">
  <h2 class="day-title"><span class="day-badge">D{index}</span>第 {index} 天</h2>
  <p class="day-subtitle">当日核心目标与节奏建议。</p>
  <div class="time-row morning">
    <div class="time-row-label">早上</div>
    <div class="time-row-text">抵达或出发后的第一段安排。</div>
  </div>
  <div class="time-row afternoon">
    <div class="time-row-label">下午</div>
    <div class="time-row-text">当天的核心游览与交通衔接。</div>
  </div>
  <div class="time-row evening">
    <div class="time-row-label">晚上</div>
    <div class="time-row-text">住宿、晚餐与第二天准备。</div>
  </div>
  <div class="day-info">
    <div class="day-info-item">
      <div class="day-info-label">吃什么</div>
      <div class="day-info-text">当地特色餐食与点餐建议。</div>
    </div>
    <div class="day-info-item">
      <div class="day-info-label">交通与预订</div>
      <div class="day-info-text">车次/门票/入住时间，以官方为准。</div>
    </div>
    <div class="day-info-item alternative">
      <div class="day-info-label">替代方案</div>
      <div class="day-info-text">天气或班次变化时删什么、保什么、移到哪里。</div>
    </div>
  </div>
</div>"""
            )

        pages.append(
            """<div class="page">
  <div class="city-header">
    <h3 class="city-title"><span class="city-name">目的地</span>｜沿途城市读本</h3>
    <p class="city-tagline">知道眼前的风景从哪里来，旅行会多出一层。</p>
  </div>
  <p class="city-intro">从历史层叠理解城市今天的面貌，传说与史实分开表述。</p>
  <h4 class="subsection-title">值得慢看的地方</h4>
  <div class="sight-name">城市核心区</div>
  <div class="sight-desc">按顺序列出主要景点，说明历史背景与常见误解。</div>
  <div class="field-notes">
    <div class="field-notes-title">站在现场，留意这些细节</div>
    <ul>
      <li>光线、材料、结构与方向感。</li>
      <li>使用者和日常生活的痕迹。</li>
      <li>修复外观与原貌的区别。</li>
    </ul>
  </div>
  <div class="viewing-order">
    <div class="viewing-order-title">建议观看顺序</div>
    <ol>
      <li>抵达后先看总体格局。</li>
      <li>再进入具体建筑与街区。</li>
      <li>最后回到交通节点。</li>
    </ol>
  </div>
</div>"""
        )

        pages.append(
            """<div class="page">
  <h2 class="section-title">预算与预订节奏</h2>
  <p class="section-subtitle">每人粗估，具体价格以官方为准</p>
  <table class="budget-table">
    <thead>
      <tr>
        <th>项目</th>
        <th>经济舒适型</th>
        <th>说明</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>交通</td><td>待补充</td><td>铁路/巴士/市内交通</td></tr>
      <tr><td>住宿</td><td>待补充</td><td>各城市住宿</td></tr>
      <tr><td>餐饮</td><td>待补充</td><td>每日餐食</td></tr>
      <tr><td>门票与体验</td><td>待补充</td><td>景点与体验项目</td></tr>
      <tr class="total-row"><td>合计</td><td>待补充</td><td>含机动金建议</td></tr>
    </tbody>
  </table>
  <h3 class="subsection-title">什么时候订</h3>
  <div class="booking-timeline-item">
    <div class="booking-timeline-marker">现在</div>
    <div class="booking-timeline-content">确认护照、签证与边境开放状态。</div>
  </div>
  <div class="booking-timeline-item">
    <div class="booking-timeline-marker">出发前 4-6 周</div>
    <div class="booking-timeline-content">预订核心车票与住宿。</div>
  </div>
  <div class="booking-timeline-item">
    <div class="booking-timeline-marker">出发前 48 小时</div>
    <div class="booking-timeline-content">离线备份车票、地图与证件扫描件。</div>
  </div>
  <div class="payment-strategy">
    <strong>付款策略：</strong>卡片/现金/换汇建议，汇率波动以官方为准。
  </div>
</div>"""
        )

        pages.append(
            """<div class="page">
  <h2 class="section-title">行李、天气与风险控制</h2>
  <p class="section-subtitle">按季节分层穿衣，出发前复核天气</p>
  <h3 class="subsection-title">分层穿衣</h3>
  <ul class="plain-list">
    <li>贴身层：排汗速干。</li>
    <li>保暖层：抓绒/轻薄羽绒。</li>
    <li>鞋类：适合城市步行与短途徒步。</li>
    <li>随身包：证件、现金、充电与离线地图。</li>
  </ul>
  <h3 class="subsection-title">关键风险</h3>
  <table class="risk-table">
    <thead>
      <tr><th>情况</th><th>处理原则</th></tr>
    </thead>
    <tbody>
      <tr><td class="risk-situation">车次晚点或取消</td><td class="risk-action">保留缓冲时间，准备替代交通。</td></tr>
      <tr><td class="risk-situation">天气突变</td><td class="risk-action">优先删室外长距离段。</td></tr>
      <tr><td class="risk-situation">证件问题</td><td class="risk-action">随身复印件 + 离线电子版。</td></tr>
    </tbody>
  </table>
  <div class="checklist">
    <h3 class="subsection-title">旅行前核对清单</h3>
    <ul>
      <li>证件与入境要求</li>
      <li>关键车票核对</li>
      <li>口岸与班次状态</li>
      <li>体验项目安全条件</li>
    </ul>
  </div>
</div>"""
        )

        pages.append(
            """<div class="page">
  <h2 class="section-title">实用链接与资料来源</h2>
  <div class="links-group">
    <h4>交通与预订</h4>
    <ul class="links-list">
      <li>铁路/巴士/住宿预订入口：以官方渠道为准。</li>
    </ul>
  </div>
  <div class="links-group">
    <h4>历史与目的地背景</h4>
    <ul class="links-list">
      <li>目的地官方旅游网站与历史资料。</li>
    </ul>
  </div>
  <div class="disclaimer">
    <strong>说明：</strong>本攻略中的时间、价格与班次可能变化，出发前请通过官方渠道复核。
  </div>
</div>"""
        )
        return "\n".join(pages).strip()


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
        )


class ResumeRecipe(PDFRecipe):
    name = "resume"
    display_name = "个人简历"
    css_template = "resume"
    color_scheme = "blue"
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
            lines.append(f'<div class="resume-section-title">核心技能</div>')
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
        TravelRecipe,
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
