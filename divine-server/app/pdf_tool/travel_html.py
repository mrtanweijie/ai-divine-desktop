from __future__ import annotations

import html as html_lib
import re

import markdown as markdown_lib
from bs4 import BeautifulSoup

_DAY_RE = re.compile(
    r"^(?:(?:Day|D)\s*(\d+)|第\s*(\d+)\s*天)\s*[·：:\-—\s]*(.*)$",
    re.IGNORECASE,
)
_EMOJI_BULLET_RE = re.compile(r"^[✦•▪○◇]\s*")
_ICON_BULLET_RE = re.compile(
    r"^(?:🏠|💡|⚠️|🛏|🚗|📌|✈|🏝)\s*"
)
_DAY_LINE_RE = re.compile(
    r"^\*{0,2}\s*(?:(?:Day|D)\s*\d+|第\s*\d+\s*天)",
    re.IGNORECASE,
)
_SECTION_LINE_RE = re.compile(
    r"^(?:路线总览|路线概览|行程概览|预算清单|酒店推荐|行前提醒|美食清单|交通小结|"
    r"行李、天气与风险控制|实用链接与资料来源|关键风险)"
)
_INFO_LINE_RE = re.compile(
    r"^(\*\*)?(?:吃什么|交通与预订|交通|预订|替代方案|备选)"
    r"(\*\*)?\s*[：:]"
)
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_TIME_LABELS = [
    ("早上", "morning"),
    ("上午", "morning"),
    ("中午", "afternoon"),
    ("下午", "afternoon"),
    ("傍晚", "evening"),
    ("晚上", "evening"),
    ("夜晚", "evening"),
]
_INFO_LABELS = [
    ("吃什么", "food"),
    ("交通与预订", "transport"),
    ("交通", "transport"),
    ("预订", "transport"),
    ("替代方案", "alternative"),
    ("备选", "alternative"),
]


def looks_like_travel_html(content: str) -> bool:
    stripped = (content or "").lstrip()
    return stripped.startswith('<div class="page"') and (
        "<div class=\"page\"" in stripped
    )


def _preprocess_markdown(markdown: str) -> str:
    lines: list[str] = []
    for raw in markdown.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append("")
            continue
        if not stripped.startswith("#") and _DAY_LINE_RE.match(stripped):
            raw = "## " + stripped.lstrip("*#").strip()
        elif not stripped.startswith("#") and _SECTION_LINE_RE.match(stripped):
            raw = "## " + stripped
        elif _EMOJI_BULLET_RE.match(stripped):
            raw = "- " + _EMOJI_BULLET_RE.sub("", stripped)
        elif _ICON_BULLET_RE.match(stripped):
            raw = "- " + _ICON_BULLET_RE.sub("", stripped)
        block_start = (
            raw.startswith(("## ", "- ", "|"))
            or bool(_INFO_LINE_RE.match(raw))
        )
        if (
            block_start
            and lines
            and lines[-1].strip()
            and not lines[-1].strip().startswith(("- ", "|"))
        ):
            lines.append("")
        lines.append(raw)
    return "\n".join(lines)


def _page_kind(text: str) -> str:
    lowered = text.lower()
    if _DAY_RE.match(text):
        return "day"
    if "预算" in text:
        return "budget"
    if any(word in lowered for word in ("行李", "天气", "风险")):
        return "risk"
    if any(word in text for word in ("链接", "资料来源", "实用链接", "来源")):
        return "links"
    if any(word in text for word in ("城市", "读本")):
        return "city"
    if "路线" in text:
        return "overview"
    return "section"


def _day_heading(text: str) -> str:
    match = _DAY_RE.match(text.strip())
    if not match:
        return html_lib.escape(text)
    number = match.group(1) or match.group(2)
    rest = match.group(3).strip() or text
    suffix = f"｜{html_lib.escape(rest)}" if rest and rest != text else ""
    return f"D{number}{suffix}"


def _day_page_open(text: str) -> str:
    return (
        f'<div class="page"><h2 class="day-title">'
        f"{_day_heading(text)}</h2>"
    )


def _route_map_html(text: str) -> str:
    parts = [
        part.strip()
        for part in re.split(r"→|->|,|、|·|/", text)
        if part.strip()
    ]
    if len(parts) < 2:
        return ""
    stops = "".join(
        f'<div class="route-stop {"above" if index % 2 == 0 else "below"}">'
        f'<span class="stop-name">{html_lib.escape(part)}</span></div>'
        for index, part in enumerate(parts)
    )
    return (
        '<div class="route-map"><div class="route-stops">'
        f'{stops}</div></div>'
    )


def _match_time_text(text: str) -> tuple[str, str, str] | None:
    compact = text.replace(" ", "")
    for label, kind in _TIME_LABELS:
        if compact == label:
            return label, kind, ""
        if compact.startswith(label + "：") or compact.startswith(label + ":"):
            rest = compact[len(label):].lstrip("：: ")
            return label, kind, rest
    return None


def _match_info_text(text: str) -> tuple[str, str, str] | None:
    compact = text.replace(" ", "")
    for label, kind in _INFO_LABELS:
        if compact == label:
            return label, kind, ""
        if compact.startswith(label + "：") or compact.startswith(label + ":"):
            rest = compact[len(label):].lstrip("：: ")
            return label, kind, rest
    return None


def _list_html(node) -> str:
    if node.name == "ol":
        return str(node)
    return str(node).replace("<ul>", '<ul class="check-list">', 1)


def _table_html(node, page_kind: str) -> str:
    table_class = {
        "budget": "budget-table",
        "risk": "risk-table",
        "overview": "route-table",
        "city": "route-table",
    }.get(page_kind, "route-table")
    return str(node).replace("<table>", f'<table class="{table_class}">', 1)


def travel_markdown_to_html(markdown: str) -> str:
    prepared = _preprocess_markdown(markdown)
    html_doc = markdown_lib.markdown(
        prepared,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    soup = BeautifulSoup(html_doc, "html.parser")
    body = soup.body or soup

    pages: list[str] = []
    blocks: list[str] = []
    page_kind = "section"
    time_row: dict[str, str | list[str]] | None = None
    time_rows: list[str] = []
    info_item: dict[str, str | list[str]] | None = None

    def close_time_row() -> None:
        nonlocal time_row
        if not time_row:
            return
        content = " ".join(time_row["texts"]) if time_row["texts"] else ""
        if content:
            time_rows.append(
                '<tr><td class="time-label">%s</td>'
                '<td class="time-content">%s</td></tr>'
                % (time_row["label"], content)
            )
        time_row = None

    def close_info_item() -> None:
        nonlocal info_item
        if not info_item:
            return
        content = " ".join(info_item["texts"]) if info_item["texts"] else ""
        if content:
            blocks.append(
                '<div class="day-section">'
                '<div class="day-section-title">%s</div>'
                '<div class="day-section-text">%s</div></div>'
                % (info_item["label"], content)
            )
        info_item = None

    def flush_page() -> None:
        nonlocal page_kind, time_row, time_rows, info_item
        close_time_row()
        close_info_item()
        if time_rows:
            blocks.append(
                '<table class="time-table">%s</table>'
                % "".join(time_rows)
            )
            time_rows = []
        if blocks:
            blocks.append("</div>")
            pages.append("\n".join(blocks))
            blocks.clear()
        page_kind = "section"

    for node in body.find_all(recursive=False):
        name = node.name
        if name == "h1":
            continue
        if name == "h2":
            flush_page()
            text = node.get_text(" ", strip=True)
            plan_match = re.match(r"^方案\s*[A-Za-z0-9]", text)
            route_match = re.match(
                r"^(?:路线总览|路线概览|行程概览)(?:[：:]\s*(.*))?$",
                text,
            )
            if plan_match or route_match:
                page_kind = "overview"
                blocks.append(
                    '<div class="page"><h2 class="section-title">路线总览</h2>'
                )
                if plan_match:
                    subtitle = text
                else:
                    subtitle = (
                        route_match.group(1).strip()
                        if route_match and route_match.group(1)
                        else ""
                    )
                if subtitle:
                    blocks.append(
                        f'<p class="section-subtitle">'
                        f"{html_lib.escape(subtitle)}</p>"
                    )
                if route_match and subtitle:
                    blocks.append(_route_map_html(subtitle))
                continue
            page_kind = _page_kind(text)
            if page_kind == "day":
                blocks.append(_day_page_open(text))
            else:
                blocks.append(
                    f'<div class="page"><h2 class="section-title">'
                    f"{html_lib.escape(text)}</h2>"
                )
            continue
        if name == "h3":
            close_time_row()
            close_info_item()
            text = node.get_text(" ", strip=True)
            time_match = _match_time_text(text)
            info_match = _match_info_text(text)
            if _DAY_RE.match(text):
                flush_page()
                page_kind = "day"
                blocks.append(_day_page_open(text))
            elif page_kind == "day" and time_match:
                time_row = {
                    "kind": time_match[1],
                    "label": time_match[0],
                    "texts": [time_match[2]] if time_match[2] else [],
                }
            elif page_kind == "day" and info_match:
                info_item = {
                    "kind": info_match[1],
                    "label": info_match[0],
                    "texts": [info_match[2]] if info_match[2] else [],
                }
            else:
                blocks.append(
                    f'<h3 class="subsection-title">'
                    f"{html_lib.escape(text)}</h3>"
                )
            continue
        if name == "p":
            text = node.get_text(" ", strip=True)
            day_match = _DAY_RE.match(text)
            if day_match:
                flush_page()
                page_kind = "day"
                blocks.append(_day_page_open(text))
                continue
            if page_kind == "overview" and re.search(r"→|->", text):
                blocks.append(_route_map_html(text))
                continue
            time_match = _match_time_text(text)
            if page_kind == "day" and time_match:
                close_time_row()
                time_row = {
                    "kind": time_match[1],
                    "label": time_match[0],
                    "texts": [time_match[2]] if time_match[2] else [],
                }
                continue
            info_match = _match_info_text(text)
            if page_kind == "day" and info_match:
                close_info_item()
                info_item = {
                    "kind": info_match[1],
                    "label": info_match[0],
                    "texts": [info_match[2]] if info_match[2] else [],
                }
                continue
            if time_row:
                time_row["texts"].append(str(node))
            elif info_item:
                info_item["texts"].append(str(node))
            else:
                blocks.append(str(node))
            continue
        if name in ("ul", "ol"):
            if page_kind == "day" and name == "ul":
                others: list[str] = []
                for item in node.find_all("li", recursive=False):
                    item_text = item.get_text(" ", strip=True)
                    time_match = _match_time_text(item_text)
                    if time_match and time_match[2]:
                        time_rows.append(
                            '<tr><td class="time-label">%s</td>'
                            '<td class="time-content">%s</td></tr>'
                            % (time_match[0], time_match[2])
                        )
                    else:
                        others.append(str(item))
                if others:
                    blocks.append(
                        '<ul class="check-list">%s</ul>' % "".join(others)
                    )
                continue
            items = [
                item.get_text(" ", strip=True)
                for item in node.find_all("li", recursive=False)
                if item.get_text(" ", strip=True)
            ]
            if time_row:
                time_row["texts"].append("；".join(items))
            elif info_item:
                info_item["texts"].append("；".join(items))
            else:
                blocks.append(_list_html(node))
            continue
        if name == "table":
            blocks.append(_table_html(node, page_kind))
            continue
        if name == "pre":
            pre_lines = [
                line.strip()
                for line in (node.get_text("\n", strip=True) or "").splitlines()
                if line.strip()
            ]
            if (
                len(pre_lines) >= 2
                and "D1" in pre_lines[0]
                and re.search(r"[─—-]+", pre_lines[1])
            ):
                parts = [
                    part.strip()
                    for part in re.split(r"[─—-]+", pre_lines[1])
                    if part.strip()
                ]
                if parts:
                    blocks.append(_route_map_html(" → ".join(parts)))
                    continue
            blocks.append(str(node))
            continue
        if name == "blockquote":
            blocks.append(f'<div class="disclaimer">{node}</div>')
            continue
        if name == "hr":
            blocks.append('<hr class="day-divider">')
            continue
        blocks.append(str(node))

    flush_page()
    if not pages:
        return f'<div class="page">{html_doc}</div>'
    return "\n".join(pages).strip()


_DAY_PROMPT_RE = re.compile(
    r"^\s*[-*]?\s*(?:Day|D)\s*(\d+)\s*[·：:\-—\s]*(.*)$",
    re.IGNORECASE,
)
_SECTION_PROMPT_RE = re.compile(r"^\s*【([^】]+)】")


def _prompt_route_map(prompt: str) -> str:
    cities: list[str] = []
    for line in prompt.splitlines():
        match = _DAY_PROMPT_RE.match(line.strip())
        if not match:
            continue
        rest = match.group(2) or ""
        title = re.split(r"[：:]", rest, maxsplit=1)[0].strip()
        first = re.split(r"[·→\-]", title)[0].strip()
        if first and first not in cities:
            cities.append(first)
    if len(cities) >= 2:
        return _route_map_html(" → ".join(cities[:8]))
    return ""


def _build_prompt_day_html(
    day: tuple[str, str, str], lines: list[str]
) -> str:
    number, title, rest = day
    time_rows: list[str] = []
    food_lines: list[str] = []
    detail_lines: list[str] = []
    for raw in lines:
        line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
        if not line:
            continue
        time_match = _match_time_text(line)
        if time_match and time_match[2]:
            time_rows.append(
                '<tr><td class="time-label">%s</td>'
                '<td class="time-content">%s</td></tr>'
                % (time_match[0], html_lib.escape(time_match[2]))
            )
        elif "午餐" in line or "晚餐" in line:
            food_lines.append(html_lib.escape(line))
        else:
            detail_lines.append(html_lib.escape(line))
    if rest:
        detail_lines.insert(0, html_lib.escape(rest))

    body = [
        f'<div class="page"><h2 class="day-title">D{number}｜'
        f"{html_lib.escape(title or f'第 {number} 天')}</h2>"
    ]
    if time_rows:
        body.append(
            '<table class="time-table">%s</table>' % "".join(time_rows)
        )
    if detail_lines:
        body.append(
            '<div class="day-section"><div class="day-section-title">行程安排</div>'
            '<div class="day-section-text">%s</div></div>'
            % "；".join(detail_lines)
        )
    if food_lines:
        body.append(
            '<div class="day-section"><div class="day-section-title">吃什么</div>'
            '<div class="day-section-text">%s</div></div>'
            % "；".join(food_lines)
        )
    body.append("</div>")
    return "\n".join(body)


def _risk_page_html() -> str:
    """P5 行李、天气与风险控制（兜底页）。"""
    return """<div class="page">
  <h2 class="section-title">行李、天气与风险控制</h2>
  <p class="section-subtitle">按季节分层穿衣，出发前复核天气</p>
  <h3 class="subsection-title">分层穿衣</h3>
  <ul class="check-list">
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
  <div class="highlight-box">
    <div class="box-title">旅行前核对清单</div>
    <ul class="check-list">
      <li>证件与入境要求</li>
      <li>关键车票核对</li>
      <li>口岸与班次状态</li>
      <li>体验项目安全条件</li>
    </ul>
  </div>
</div>"""


def closing_pages_html() -> str:
    """核心收尾页：行李、天气与风险控制（模板 P5），供兜底输出补全结构。"""
    return _risk_page_html()


def travel_prompt_to_html(prompt: str) -> str:
    lines = prompt.splitlines()
    day_pages: list[str] = []
    current_day: tuple[str, str, str] | None = None
    current_lines: list[str] = []
    section_title = ""
    section_lines: list[str] = []
    section_pages: list[str] = []

    def flush_day() -> None:
        nonlocal current_day, current_lines
        if current_day:
            day_pages.append(_build_prompt_day_html(current_day, current_lines))
        current_day = None
        current_lines = []

    def flush_section() -> None:
        nonlocal section_title, section_lines
        if section_title and section_lines:
            items = "".join(
                f"<li>{html_lib.escape(line)}</li>"
                for line in section_lines
                if line.strip()
            )
            section_pages.append(
                f'<div class="page"><h2 class="section-title">'
                f"{html_lib.escape(section_title)}</h2>"
                f'<ul class="check-list">{items}</ul></div>'
            )
        section_title = ""
        section_lines = []

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        day_match = _DAY_PROMPT_RE.match(stripped)
        section_match = _SECTION_PROMPT_RE.match(stripped)
        if day_match:
            flush_section()
            flush_day()
            rest = day_match.group(2) or ""
            title = rest
            content = ""
            if "：" in rest or ":" in rest:
                title, content = re.split(r"[：:]", rest, maxsplit=1)
            current_day = (
                day_match.group(1),
                title.strip(),
                content.strip(),
            )
        elif section_match:
            flush_section()
            flush_day()
            section_title = section_match.group(1).strip()
        elif current_day is not None:
            current_lines.append(stripped)
        elif section_title:
            section_lines.append(
                re.sub(r"^\s*[-*]\s+", "", stripped)
            )
    flush_day()
    flush_section()

    route_map = _prompt_route_map(prompt)
    overview = [
        '<div class="page"><h2 class="section-title">路线总览</h2>',
        '<p class="section-subtitle">完整旅行手册｜全程信息以官方为准</p>',
    ]
    if route_map:
        overview.append(route_map)
    overview.append(
        '<div class="highlight-box"><div class="box-title">路线逻辑</div>'
        '<ul class="check-list">'
        "<li><strong>自然：</strong>沿途地理与气候主线。</li>"
        "<li><strong>历史：</strong>丝路城市的历史层次。</li>"
        "<li><strong>文化：</strong>当地生活与少数族群观察。</li>"
        "<li><strong>节奏：</strong>每天保留替代方案，避免被天气或班次打乱。</li>"
        "</ul></div>"
    )
    overview.append("</div>")

    pages = "\n".join([*overview, *day_pages, *section_pages]).strip()
    # 补全核心收尾页：行李、天气与风险控制（prompt 已生成则跳过，避免重复）
    if "行李" not in pages and "风险" not in pages:
        pages += "\n" + _risk_page_html()
    return pages
