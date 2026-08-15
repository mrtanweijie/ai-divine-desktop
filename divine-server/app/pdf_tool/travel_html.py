from __future__ import annotations

import html as html_lib
import re

import markdown as markdown_lib
from bs4 import BeautifulSoup

_DAY_RE = re.compile(r"^(?:Day|D)\s*(\d+)\s*[·：:\-—\s]*(.*)$", re.IGNORECASE)
_EMOJI_BULLET_RE = re.compile(r"^[✦•▪○◇]\s*")
_ICON_BULLET_RE = re.compile(
    r"^(?:🏠|💡|⚠️|🛏|🚗|📌|✈|🏝)\s*"
)
_DAY_LINE_RE = re.compile(r"^\*{0,2}\s*(?:Day|D)\s*\d+", re.IGNORECASE)
_SECTION_LINE_RE = re.compile(
    r"^(?:路线总览|预算清单|酒店推荐|行前提醒|美食清单|交通小结|"
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
    number = match.group(1)
    rest = match.group(2).strip() or text
    return (
        f'<span class="day-badge">D{number}</span>'
        f"{html_lib.escape(rest)}"
    )


def _match_time_text(text: str) -> tuple[str, str, str] | None:
    for label, kind in _TIME_LABELS:
        if text == label:
            return label, kind, ""
        if text.startswith(label + "：") or text.startswith(label + ":"):
            rest = text[len(label):].lstrip("：: ")
            return label, kind, rest
    return None


def _match_info_text(text: str) -> tuple[str, str, str] | None:
    for label, kind in _INFO_LABELS:
        if text == label:
            return label, kind, ""
        if text.startswith(label + "：") or text.startswith(label + ":"):
            rest = text[len(label):].lstrip("：: ")
            return label, kind, rest
    return None


def _list_html(node) -> str:
    if node.name == "ol":
        return str(node)
    return str(node).replace("<ul>", '<ul class="plain-list">', 1)


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
    info_item: dict[str, str | list[str]] | None = None

    def close_time_row() -> None:
        nonlocal time_row
        if not time_row:
            return
        content = " ".join(time_row["texts"]) if time_row["texts"] else ""
        if content:
            blocks.append(
                '<div class="time-row %s">'
                '<div class="time-row-label">%s</div>'
                '<div class="time-row-text">%s</div></div>'
                % (time_row["kind"], time_row["label"], content)
            )
        time_row = None

    def close_info_item() -> None:
        nonlocal info_item
        if not info_item:
            return
        content = " ".join(info_item["texts"]) if info_item["texts"] else ""
        if content:
            extra = " alternative" if info_item["kind"] == "alternative" else ""
            blocks.append(
                '<div class="day-info-item%s">'
                '<div class="day-info-label">%s</div>'
                '<div class="day-info-text">%s</div></div>'
                % (extra, info_item["label"], content)
            )
        info_item = None

    def flush_page() -> None:
        nonlocal page_kind, time_row, info_item
        close_time_row()
        close_info_item()
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
            route_match = re.match(r"^路线总览[：:]\s*(.*)$", text)
            if plan_match or route_match:
                page_kind = "overview"
                blocks.append(
                    '<div class="page"><h2 class="section-title">路线总览</h2>'
                )
                subtitle = (
                    route_match.group(1).strip() if route_match else text
                )
                if subtitle:
                    blocks.append(
                        f'<p class="section-subtitle">'
                        f"{html_lib.escape(subtitle)}</p>"
                    )
                continue
            page_kind = _page_kind(text)
            if page_kind == "day":
                blocks.append(
                    f'<div class="page day-block"><h2 class="day-title">'
                    f"{_day_heading(text)}</h2>"
                )
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
                blocks.append(
                    f'<div class="page day-block"><h2 class="day-title">'
                    f"{_day_heading(text)}</h2>"
                )
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
                blocks.append(
                    f'<div class="page day-block"><h2 class="day-title">'
                    f"{_day_heading(text)}</h2>"
                )
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
