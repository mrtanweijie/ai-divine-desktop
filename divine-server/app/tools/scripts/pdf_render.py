import json
import html as html_lib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.docgen.pdf.renderer import render_html_to_pdf, render_markdown_to_pdf  # noqa: E402


_COVER_START_RE = re.compile(r"^\s*(<div\b[^>]*>)", re.IGNORECASE)
_DIV_TAG_RE = re.compile(r"<(/?)div\b[^>]*>", re.IGNORECASE)
_FULL_WIDTH_RE = re.compile(r"width\s*:\s*100%", re.IGNORECASE)
_FULL_HEIGHT_RE = re.compile(r"height\s*:\s*100%", re.IGNORECASE)
_PAGE_BREAK_RE = re.compile(r"page-break-after\s*:\s*always", re.IGNORECASE)
_TITLE_FONT_RE = re.compile(
    r"font-size\s*:\s*(?:3[6-9]|4\d|5[0-2])px[^>]*>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
_OWN_TOC_RE = re.compile(r"(?ms)^#\s*目录\s*$.*?(?=^#\s|\Z)")


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def _plain_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def _extract_leading_cover(content: str) -> tuple[str, str]:
    """识别正文开头的整页 HTML 封面，返回 (cover_html, 剩余正文)。"""
    text = content or ""
    start = _COVER_START_RE.search(text)
    if not start:
        return "", text
    start_pos = start.start(1)
    depth = 0
    for tag in _DIV_TAG_RE.finditer(text, start_pos):
        if tag.group(1):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            cover = text[start_pos : tag.end()]
            style = start.group(1).lower()
            if (
                _FULL_WIDTH_RE.search(style)
                and _FULL_HEIGHT_RE.search(style)
                and _PAGE_BREAK_RE.search(style)
            ):
                rest = text[tag.end() :].lstrip("\n")
                return cover, rest
            return "", text
    return "", text


def _title_from_cover(cover: str) -> str:
    match = _TITLE_FONT_RE.search(cover or "")
    raw = match.group(1) if match else cover or ""
    return _plain_text(raw)[:60]


def _strip_own_toc(markdown: str) -> str:
    """有自动目录时移除正文里重复的“# 目录”小节。"""
    return _OWN_TOC_RE.sub("", markdown or "").lstrip("\n")


def derive_title(title: str, content: str) -> str:
    candidate = (title or "").strip()
    if candidate:
        if "<" in candidate:
            candidate = _plain_text(candidate)
        return candidate
    cover, rest = _extract_leading_cover(content)
    if cover:
        candidate = _title_from_cover(cover)
        if candidate:
            return candidate
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if "<" in stripped:
            plain = _plain_text(stripped)
            if plain:
                return plain[:60]
            continue
        if stripped:
            return stripped[:60]
    return "PDF文档"


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    content = str(params.get("content") or params.get("markdown") or "").strip()
    raw_file = str(params.get("file_path") or "").strip()
    base_dir = workspace
    if not content and raw_file:
        source = Path(raw_file)
        if not source.is_absolute():
            source = workspace / source
        source = source.resolve()
        if not source.is_file():
            print(
                json.dumps(
                    {"success": False, "message": f"文件不存在: {source}"},
                    ensure_ascii=False,
                )
            )
            return
        content = source.read_text(encoding="utf-8")
        base_dir = source.parent
    if not content.strip():
        print(
            json.dumps(
                {"success": False, "message": "缺少 Markdown 内容或 file_path"},
                ensure_ascii=False,
            )
        )
        return

    cover_html, content = _extract_leading_cover(content)
    title = derive_title(str(params.get("title") or ""), cover_html + "\n" + content)
    output_dir = output_root / "pdf"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace.resolve())
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return
    if output_dir.exists() and not output_dir.is_dir():
        print(
            json.dumps(
                {"success": False, "message": f"保存路径不是目录: {output_dir}"},
                ensure_ascii=False,
            )
        )
        return
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = str(params.get("file_name") or "").strip() or title
    file_name = re.sub(r"\.md$", "", file_name, flags=re.IGNORECASE)
    # 若 file_name 是完整需求句（超长或含 prompt 特征），退回用 title 并截断
    if (
        len(file_name) > 40
        or re.search(r"(为|请|帮我).{0,6}(生成|制作|写|输出)|\.pdf$", file_name)
    ) and title:
        file_name = title
    file_name = file_name[:40]
    output_path = unique_output_path(output_dir, file_name, "PDF文档", ".pdf")
    cover_data = dict(params.get("cover_data") or {})
    if cover_html:
        cover_data["cover_html"] = cover_html
    cover = bool(params.get("cover")) or bool(cover_html)
    toc = bool(params.get("toc"))
    if toc and cover_html:
        content = _strip_own_toc(content)
    try:
        theme = str(params.get("theme") or params.get("style") or "universal")
        if theme in ("universal", "modern") and any(
            keyword in f"{title}\n{content}"
            for keyword in ("旅行", "旅游", "攻略", "行程", "目的地")
        ):
            theme = "travel"
        if theme.startswith("travel"):
            from app.docgen.pdf.theme_manager import travel_color_overrides
            from app.docgen.pdf.travel_html import (
                looks_like_travel_html,
                travel_markdown_to_html,
            )

            if not looks_like_travel_html(content):
                content = travel_markdown_to_html(content)
            cover_data = dict(params.get("cover_data") or {})
            cover_data.setdefault("title", title)
            overrides = travel_color_overrides(
                str(params.get("color_scheme") or "teal"),
                params.get("theme_colors") or None,
                theme=theme,
            )
            meta = render_html_to_pdf(
                content,
                output_path,
                title=title,
                paper_size=str(params.get("paper_size") or "A4"),
                cover=cover,
                cover_data=cover_data,
                base_dir=base_dir,
                theme=theme,
                overrides=overrides,
            )
        else:
            from app.docgen.pdf.theme_manager import universal_color_overrides

            meta = render_markdown_to_pdf(
                content,
                output_path,
                title=title,
                style=str(params.get("style") or "modern"),
                color_scheme=str(params.get("color_scheme") or "blue"),
                paper_size=str(params.get("paper_size") or "A4"),
                cover=cover,
                toc=toc,
                base_dir=base_dir,
                theme=theme,
                cover_data=cover_data,
                overrides=universal_color_overrides(
                    params.get("theme_colors")
                )
                or None,
            )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"PDF 渲染失败: {exc}",
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return
    print(
        json.dumps(
            {
                "success": True,
                "message": "PDF 渲染完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": meta,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
