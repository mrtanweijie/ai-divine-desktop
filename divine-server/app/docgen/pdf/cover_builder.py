"""封面与旅行版式构建：封面 HTML、占位图内联、travel 文档 HTML 组装。

从 theme_manager.py（原 2,039 行单文件）拆出。
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any
from .theme_registry import get_theme_manager, load_theme_css

COVER_TEMPLATES: dict[str, str] = {
    "resume": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{theme_name}</div>
    </div>
    """,
    "universal": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">{badge}</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="meta">
          <span>PDF</span>
          <span class="meta-divider"></span>
          <span>{theme_name}</span>
          <span class="meta-divider"></span>
          <span>AI Divine</span>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    """,
    "modern": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">{badge}</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="meta">
          <span>PDF</span>
          <span class="meta-divider"></span>
          <span>{theme_name}</span>
          <span class="meta-divider"></span>
          <span>AI Divine</span>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    """,
    "notion": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{date}</div>
    </div>
    """,
    "linear": """
    <div class="cover">
      <div class="badge">{badge}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{theme_name} · AI Divine</div>
    </div>
    """,
    "apple": """
    <div class="cover">
      <div class="badge">{badge}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">
        <span>PDF</span>
        <span class="meta-divider"></span>
        <span>{theme_name}</span>
        <span class="meta-divider"></span>
        <span>AI Divine</span>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    """,
    "academic": """
    <div class="cover">
      <div class="institution">{institution}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="author-block">
        <div class="name">{author}</div>
        <div>{affiliation}</div>
      </div>
      <div class="date">{date}</div>
    </div>
    """,
    "travel": """
    <div class="page cover">
      <div class="cover-band">
        <div class="cover-countries">{countries}</div>
        <h1 class="cover-title">{title}</h1>
        <div class="cover-meta">{meta_line}</div>
      </div>
    </div>
    """,
    "travel_mag": """
    <div class="page cover">
      <div class="cover-hero">
        <div class="hero-kicker">Travel Handbook · 2026</div>
        <div class="hero-watermark">{watermark}</div>
      </div>
      <div class="cover-band">
        <div class="cover-countries">{countries}</div>
        <h1 class="cover-title">{title}</h1>
        <div class="cover-meta">{meta_line}</div>
      </div>
      <div class="cover-body">
        <div class="cover-tagline">{meta_secondary}</div>
        <p class="cover-summary">{summary}</p>
        <div class="stat-row">{stat_pills}</div>
      </div>
    </div>
    """,
    "roadmap": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">学习路线</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="roadmap-meta">
          <div class="meta-item">周期：{total_weeks}</div>
          <div class="meta-item">节点：{total_nodes}</div>
          <div class="meta-item">目标：{goal}</div>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    """,
    "minimal": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{date}</div>
    </div>
    """,
}


def _watermark_from_title(title: str) -> str:
    """从标题提取封面水印简称。

    规则：优先取第一个分隔符（·｜|-—/空格）前的主体地名；
    否则去掉“数字+日/天/晚”的时长后缀；再退化为去掉数字后取前 4 个字符；
    兜底“旅行”。避免 170px 大字号水印被截断（如只显示前 2 字）。
    """
    text = str(title or "").strip()
    if not text:
        return "旅行"
    for sep in ("·", "｜", "|", "-", "—", "—", "/", " "):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    # 去掉时长后缀（阿拉伯数字或中文数字 + 日/天/晚），如“5日游”“十二日”
    m = re.search(r"(?:\d+|[零一二三四五六七八九十百千万两]+)\s*[日天晚]", text)
    if m:
        text = text[: m.start()].strip()
    text = re.sub(r"\d+", "", text)
    if not text:
        return "旅行"
    return text[:4] or "旅行"


_COVER_STYLES: tuple[str, ...] = (
    "left-aligned",
    "centered",
    "split",
    "minimal",
    "hero-graphic",
    "terminal",
)


def _esc_cover(value: Any) -> str:
    return html_lib.escape(str(value or ""))


def _build_style_cover(
    style: str,
    title: str,
    subtitle: str,
    data: dict[str, Any],
) -> str:
    """按 cover.style 渲染通用文档封面（非旅行/简历）。"""
    esc = _esc_cover
    # title/subtitle 由调用方（weasyprint.py）预先转义，此处不重复转义；
    # cover_data 内字段（badge/meta/highlight 等）由本函数转义。
    title_s = title
    subtitle_s = subtitle
    badge = esc(data.get("badge") or "PDF")
    # inline style 强制覆盖主题 h1 的负 letter-spacing 与 nowrap（WeasyPrint 会在
    # 空格处错误断行）；white-space:normal 保证长标题在封面宽度内换行不越界。
    _h1_style = (
        ' style="letter-spacing:0;white-space:normal;max-width:100%;'
        'overflow-wrap:break-word;word-break:break-word"'
    )
    _sub_style = (
        ' style="white-space:normal;overflow-wrap:break-word;word-break:break-word"'
    )

    if style == "left-aligned":
        meta = data.get("meta") or data.get("cover_meta") or {}
        meta_items = ""
        if isinstance(meta, dict):
            meta_items = "".join(
                f'<div class="meta-item"><span class="meta-label">{esc(k)}</span>'
                f'<span class="meta-value">{esc(v)}</span></div>'
                for k, v in meta.items()
            )
        footer = esc(data.get("footer") or "")
        footer_html = f'<div class="bottom-mark">{footer}</div>' if footer else ""
        return (
            '<div class="cover-left">'
            '<div class="accent-bar"></div>'
            f'<span class="badge">{badge}</span>'
            f"<h1{_h1_style}>{title_s}</h1>"
            f'<p class="subtitle"{_sub_style}>{subtitle_s}</p>'
            f"{f'<div class=\"meta\">{meta_items}</div>' if meta_items else ''}"
            f"{footer_html}</div>"
        )

    if style == "centered":
        issue = esc(data.get("issue_no") or "")
        author = esc(data.get("author") or "AI Divine")
        avatar = esc(data.get("avatar") or (author[:1] or "A"))
        date = esc(data.get("date") or "")
        return (
            '<div class="cover-centered">'
            f"{f'<div class=\"issue-no\">{issue}</div>' if issue else ''}"
            f"<h1{_h1_style}>{title_s}</h1>"
            '<div class="divider-line"></div>'
            f'<p class="subtitle"{_sub_style}>{subtitle_s}</p>'
            f'<div class="author-block"><div class="author-avatar">{avatar}</div>'
            f'<span class="author-name">{author}</span></div>'
            f"{f'<div class=\"date\">{date}</div>' if date else ''}"
            "</div>"
        )

    if style == "split":
        meta = data.get("meta") or {}
        meta_rows = ""
        if isinstance(meta, dict):
            meta_rows = "".join(
                f'<div class="meta-row"><span class="lbl">{esc(k)}</span>'
                f'<span class="val">{esc(v)}</span></div>'
                for k, v in meta.items()
            )
        hl = data.get("highlight") or {}
        stat_rows = ""
        stats = hl.get("stats") if isinstance(hl, dict) else None
        if isinstance(stats, list):
            stat_rows = "".join(
                f'<div class="stat-mini"><span class="lbl">{esc(s.get("label", ""))}</span>'
                f'<span class="val">{esc(s.get("value", ""))}</span></div>'
                for s in stats
                if isinstance(s, dict)
            )
        right = ""
        if isinstance(hl, dict) and hl.get("value"):
            right = (
                '<div class="right-panel">'
                f'<div class="highlight-num">{esc(hl.get("value"))}</div>'
                f'<div class="highlight-label">{esc(hl.get("label") or "")}</div>'
                f"{stat_rows}</div>"
            )
        else:
            # 无 highlight 数据：右侧主色面板兜底展示 徽标/作者/日期，避免空白
            fallback_stats = []
            for lbl, key in (("文档", "badge"), ("作者", "author"), ("日期", "date")):
                value = data.get(key)
                if value:
                    fallback_stats.append((lbl, str(value)))
            if fallback_stats:
                stat_minis = "".join(
                    f'<div class="stat-mini"><span class="lbl">{esc(lbl)}</span>'
                    f'<span class="val">{esc(val)}</span></div>'
                    for lbl, val in fallback_stats
                )
                right = (
                    '<div class="right-panel">'
                    f'<div class="highlight-num">{badge}</div>'
                    f'<div class="highlight-label">{esc(data.get("author") or "")}</div>'
                    f"{stat_minis}</div>"
                )
        return (
            '<div class="cover-split"><div class="left-panel">'
            f'<span class="badge">{badge}</span>'
            f"<h1{_h1_style}>{title_s}</h1>"
            f'<p class="subtitle"{_sub_style}>{subtitle_s}</p>'
            f"{f'<div class=\"meta-stack\">{meta_rows}</div>' if meta_rows else ''}"
            f"</div>{right}</div>"
        )

    if style == "minimal":
        doc_type = esc(data.get("doc_type") or "")
        info = data.get("info") or {}
        info_items = ""
        if isinstance(info, dict):
            info_items = "".join(
                f'<div class="info-item"><span class="info-label">{esc(k)}</span>'
                f'<span class="info-value">{esc(v)}</span></div>'
                for k, v in info.items()
            )
        return (
            '<div class="cover-minimal">'
            f"{f'<div class=\"doc-type\">{doc_type}</div>' if doc_type else ''}"
            f"<h1{_h1_style}>{title_s}</h1>"
            f'<p class="subtitle"{_sub_style}>{subtitle_s}</p>'
            f"{f'<div class=\"info-row\">{info_items}</div>' if info_items else ''}"
            "</div>"
        )

    if style == "hero-graphic":
        cta = esc(data.get("cta_text") or "")
        dots = "".join("<span></span>" for _ in range(36))
        return (
            '<div class="cover-hero">'
            '<div class="deco-circle"></div><div class="deco-circle-2"></div>'
            f'<div class="deco-dots">{dots}</div>'
            f'<span class="badge">{esc(data.get("badge") or "LAUNCH")}</span>'
            f"<h1{_h1_style}>{title_s}</h1>"
            f'<p class="subtitle"{_sub_style}>{subtitle_s}</p>'
            f"{f'<div class=\"hero-cta\"><span class=\"cta-text\">{cta}</span></div>' if cta else ''}"
            '<div class="scroll-hint"><span>SCROLL</span><div class="scroll-line"></div></div>'
            "</div>"
        )

    # terminal
    tt = esc(data.get("terminal_title") or "~/projects/docs — zsh")
    prompt = esc(data.get("prompt") or "cat ./README.md")
    outputs = data.get("output_lines") or []
    output_html = ""
    if isinstance(outputs, list):
        output_html = "".join(
            f'<span class="{esc(o.get("type", "info"))}">{esc(o.get("text", ""))}</span><br>'
            for o in outputs
            if isinstance(o, dict)
        )
    meta = data.get("meta") or {}
    meta_items = ""
    if isinstance(meta, dict):
        meta_items = "".join(
            f'<div class="item"><span class="lbl">{esc(k)}</span>'
            f'<span class="val">{esc(v)}</span></div>'
            for k, v in meta.items()
        )
    return (
        '<div class="cover-terminal"><div class="terminal-bar">'
        '<div class="terminal-dot r"></div><div class="terminal-dot y"></div>'
        '<div class="terminal-dot g"></div>'
        f'<span class="terminal-title">{tt}</span></div>'
        '<div class="terminal-body">'
        f'<div class="prompt-line"><span class="ps1">$</span> {prompt}</div>'
        f"<h1{_h1_style}>{title_s}</h1>"
        f"{f'<div class=\"output\">{output_html}</div>' if output_html else ''}"
        f"{f'<div class=\"meta-grid\">{meta_items}</div>' if meta_items else ''}"
        "</div></div>"
    )


def build_cover_html(
    theme_id: str,
    title: str,
    subtitle: str = "",
    cover_data: dict[str, Any] | None = None,
) -> str:
    # 通用文档封面风格（非旅行/简历）：cover_data.cover_style 指定
    style = ""
    if cover_data and theme_id not in ("travel", "travel_mag", "resume"):
        style = str(cover_data.get("cover_style") or "").strip()
    if style in _COVER_STYLES:
        return _build_style_cover(style, title, subtitle, cover_data or {})
    theme = get_theme_manager().get_theme(theme_id)
    template = COVER_TEMPLATES.get(theme_id, COVER_TEMPLATES["universal"])
    data = {
        "title": title,
        "subtitle": subtitle,
        "badge": "PDF",
        "theme_name": theme.display_name,
        "author": "AI Divine",
        "affiliation": "",
        "date": "",
        "institution": "",
        "destination": "",
        "duration": "",
        "travelers": "",
        "dates": "",
        "countries": "",
        "meta_line": "",
        "meta_secondary": "",
        "route_tags": "",
        "summary": subtitle,
        "total_weeks": "",
        "total_nodes": "",
        "goal": "",
    }
    extra = dict(cover_data or {})
    route = extra.pop("route", None)
    if isinstance(route, list):
        tags = [
            str(item).strip()
            for item in route
            if item is not None and str(item).strip()
        ]
        extra["route_tags"] = (
            "".join(
                f'<span class="cover-tag">{html_lib.escape(tag)}</span>'
                for tag in tags
            )
            if tags
            else ""
        )
        if not extra.get("countries") and tags:
            extra["countries"] = " × ".join(tags[:2])
    if not extra.get("meta_line"):
        dates = str(extra.get("dates") or "").strip()
        tags = extra.get("tags")
        if isinstance(tags, list):
            tags = [str(t).strip() for t in tags if str(t).strip()]
        elif isinstance(tags, str):
            tags = [
                part.strip()
                for part in re.split(r"[,、×xX/]", tags)
                if part.strip()
            ]
        else:
            tags = []
        tag_line = " × ".join(tags)
        if tag_line and dates:
            extra["meta_line"] = f"{tag_line}｜{dates}"
        elif tag_line:
            extra["meta_line"] = tag_line
        elif dates:
            extra["meta_line"] = dates
        else:
            dest = str(extra.get("destination") or "").strip()
            dur = str(extra.get("duration") or "").strip()
            joined = " · ".join(part for part in (dest, dur) if part)
            extra["meta_line"] = joined or subtitle or "AI Divine 生成文档"
    extra["summary"] = str(extra.get("summary") or subtitle or "").strip()
    extra["meta_secondary"] = str(
        extra.get("meta_secondary") or extra.get("route_constraint") or ""
    ).strip()
    for key, value in list(extra.items()):
        if key == "route_tags" or value is None:
            continue
        extra[key] = html_lib.escape(str(value))
    data.update(extra)
    if theme_id == "travel_mag":
        # 水印优先用 LLM 提供的真实简称（2-6 字），否则从标题智能提取
        wm = str(data.get("watermark") or "").strip()
        wm = re.sub(r"\s+", "", wm)
        if not (2 <= len(wm) <= 6):
            wm = _watermark_from_title(data.get("title") or "")
        data["watermark"] = wm
        # meta_line 的标签部分转成 .tag 胶囊：`标签1 × 标签2｜日期` → tag spans + ｜日期
        meta_line = data.get("meta_line") or ""
        if "｜" in meta_line:
            tag_part, _, date_part = meta_line.partition("｜")
            tags_html = "".join(
                f'<span class="tag">{t.strip()}</span>'
                for t in re.split(r"×|x|X", tag_part)
                if t.strip()
            )
            if tags_html:
                data["meta_line"] = f"{tags_html}｜{date_part}"
        pills: list[str] = []
        days = str(data.get("days") or "").strip()
        countries = str(data.get("countries") or "").strip()
        duration = str(data.get("duration") or "").strip()
        distance = str(data.get("distance") or "").strip()
        cities = str(data.get("city_count") or "").strip()
        transport = str(data.get("transport") or "").strip()
        if days:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>全程 <b>{days}</b> 天</span>'
            )
        if countries:
            country_count = len(
                [p for p in re.split(r"[×xX×,]", countries) if p.strip()]
            )
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span><b>{country_count}</b> 国</span>'
            )
        if duration:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>{duration}</span>'
            )
        if distance:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>约 <b>{distance}</b> km</span>'
            )
        if cities:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span><b>{cities}</b> 座城市</span>'
            )
        if transport:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>交通 <b>{transport}</b></span>'
            )
        data["stat_pills"] = "\n      ".join(pills)
    return template.format(**data)


_IMG_SRC_RE = re.compile(
    r'<img\b[^>]*?\bsrc=(["\'])(.*?)\1[^>]*>',
    re.IGNORECASE | re.DOTALL,
)


_PLACEHOLDER_RE = re.compile(
    r'<div class="photo-placeholder">(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def _fetch_image_data(src: str) -> tuple[bytes, str] | None:
    """下载图片，返回 (data, content_type)；失败/非图片/超限返回 None。"""
    try:
        import urllib.request

        request = urllib.request.Request(
            src,
            headers={"User-Agent": "Mozilla/5.0 (Divine PDF Renderer)"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            data = response.read(2 * 1024 * 1024 + 1)  # 上限 2MB
            if len(data) > 2 * 1024 * 1024:
                return None
            ctype = response.headers.get("Content-Type", "") or ""
            if not ctype.startswith("image/"):
                return None
        return data, ctype
    except Exception:
        return None


def _image_data_uri(src: str) -> str | None:
    fetched = _fetch_image_data(src)
    if not fetched:
        return None
    import base64

    data, ctype = fetched
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"


def _keyword_to_image_url(keyword: str) -> str:
    """把景点关键词转成稳定的图片 URL。

    优先 Unsplash（若关键词本身是 unsplash photo 链接则直接用）；
    否则用 picsum.photos 的 seed 模式（按关键词生成固定图，无需 API key），
    seed 用 URL 编码的中文+英文关键词，保证同景点多次生成图片一致。
    """
    from urllib.parse import quote

    keyword = (keyword or "").strip()
    if keyword.startswith(("http://", "https://")):
        return keyword
    seed = quote(keyword or "travel", safe="")
    return f"https://picsum.photos/seed/{seed}/900/600"


def _ensure_placeholder_blocks(html_body: str) -> str:
    """LLM 有时会省略 photo-placeholder（即使提示词要求）。

    对每个 day-title，若其所在 page 内没有 photo-placeholder，
    在 day-title 闭合后自动插入一个渐变占位（含 photo-note），
    保证配图逻辑有占位可处理。
    """
    if 'class="day-title"' not in html_body:
        return html_body

    # 一次性收集所有 (day 标题, 插入位置)，从后往前插入避免位置漂移
    insertions: list[tuple[int, str]] = []
    for m in re.finditer(
        r'<h2[^>]*class="day-title"[^>]*>(.*?)</h2>',
        html_body,
        re.DOTALL,
    ):
        insert_at = m.end()
        # 当前 page 范围（到下一个 page 开头）：判断该页是否已有 placeholder
        page_end = html_body.find('<div class="page">', insert_at)
        if page_end == -1:
            page_end = len(html_body)
        if "photo-placeholder" in html_body[insert_at:page_end]:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = html_lib.unescape(title).strip()
        title = re.sub(r"\s+", " ", title)
        placeholder = (
            '<div class="photo-placeholder">'
            f'<span class="photo-note">Photo · {title or "当日看点"}</span>'
            "</div>"
        )
        insertions.append((insert_at, "\n  " + placeholder))

    for insert_at, block in sorted(insertions, reverse=True):
        html_body = html_body[:insert_at] + block + html_body[insert_at:]
    return html_body


def _inline_placeholder_images(html_body: str, auto_fill: bool = True) -> str:
    """处理 photo-placeholder 的图片：

    1. 已有 <img>：下载外链转 base64 内嵌（成功 → PDF 离线可用；失败 → 移除 img）；
    2. 无 <img> 且 auto_fill=True（用户要求配图）：默认从 photo-note 提取关键词，
       生成图片 URL 下载内嵌（成功 → 有图；失败 → 保留渐变占位）。
       auto_fill=False（默认首轮）：保持渐变占位，不自动下载。
    CSS 无法检测 <img> 加载失败（坏链会渲染成白块盖住渐变），必须在渲染前处理。
    """
    # 先兜底：LLM 省略 placeholder 时自动插入（确保配图有占位可处理）
    html_body = _ensure_placeholder_blocks(html_body)
    if "photo-placeholder" not in html_body:
        return html_body

    def _inline_existing(match: re.Match[str]) -> str:
        tag = match.group(0)
        src = (match.group(2) or "").strip()
        if not src:
            return ""
        if src.startswith("data:") or src.startswith("file:"):
            return tag
        if not src.startswith(("http://", "https://")):
            # 本地相对路径：交给 WeasyPrint base_url 解析
            return tag
        uri = _image_data_uri(src)
        if not uri:
            return ""
        return re.sub(
            r'\bsrc=(["\'])(.*?)\1',
            f'src="{uri}"',
            tag,
            count=1,
            flags=re.IGNORECASE,
        )

    # 先处理已有 img（下载或移除）
    if "<img" in html_body:
        html_body = _IMG_SRC_RE.sub(_inline_existing, html_body)

    # 再给没有 img 的 placeholder 自动补图（仅用户要求配图时）
    if not auto_fill:
        return html_body

    def _fill_placeholder(match: re.Match[str]) -> str:
        inner = match.group(1)
        if "<img" in inner:
            return match.group(0)
        note = re.search(
            r'photo-note[^>]*>(.*?)<',
            inner,
            re.IGNORECASE | re.DOTALL,
        )
        keyword = note.group(1).strip() if note else ""
        # 去 HTML 实体与装饰符，保留景点关键词
        keyword = html_lib.unescape(keyword)
        keyword = re.sub(r"[·｜|×•—\-–\s]+", " ", keyword).strip()
        url = _keyword_to_image_url(keyword)
        uri = _image_data_uri(url)
        if not uri:
            return match.group(0)  # 下载失败：保留渐变占位
        return (
            '<div class="photo-placeholder">'
            f'<img src="{uri}" alt=""/>'
            f"{inner}</div>"
        )

    return _PLACEHOLDER_RE.sub(_fill_placeholder, html_body)


def build_travel_html_document(
    html_body: str,
    title: str,
    subtitle: str = "AI Divine 生成文档",
    cover_data: dict[str, Any] | None = None,
    include_cover: bool = True,
    overrides: dict[str, str] | None = None,
    theme: str = "travel",
    images: bool = False,
) -> str:
    css = load_theme_css(theme, overrides=overrides)
    cover_html = (
        build_cover_html(theme, html_lib.escape(title), subtitle, cover_data)
        if include_cover
        else ""
    )
    # 图片占位/配图仅旅行杂志风（travel_mag）使用：
    # 经典模板（travel）没有 photo-placeholder 样式，插入会显示原始文本。
    if theme == "travel_mag":
        html_body = _inline_placeholder_images(html_body, auto_fill=images)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        f"{cover_html}"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{html_body}</body></html>"
    )
