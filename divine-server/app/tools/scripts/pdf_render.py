import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.pdf_renderer import render_html_to_pdf, render_markdown_to_pdf  # noqa: E402


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def derive_title(title: str, content: str) -> str:
    candidate = (title or "").strip()
    if candidate:
        return candidate
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
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

    title = derive_title(str(params.get("title") or ""), content)
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
    output_path = unique_output_path(output_dir, file_name, "PDF文档", ".pdf")
    try:
        theme = str(params.get("theme") or params.get("style") or "universal")
        if theme in ("universal", "modern") and any(
            keyword in f"{title}\n{content}"
            for keyword in ("旅行", "旅游", "攻略", "行程", "目的地")
        ):
            theme = "travel"
        if theme == "travel":
            from app.pdf_theme_manager import travel_color_overrides
            from app.pdf_tool.travel_html import (
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
            )
            meta = render_html_to_pdf(
                content,
                output_path,
                title=title,
                paper_size=str(params.get("paper_size") or "A4"),
                cover=bool(params.get("cover")),
                cover_data=cover_data,
                base_dir=base_dir,
                theme="travel",
                overrides=overrides,
            )
        else:
            meta = render_markdown_to_pdf(
                content,
                output_path,
                title=title,
                style=str(params.get("style") or "modern"),
                color_scheme=str(params.get("color_scheme") or "blue"),
                paper_size=str(params.get("paper_size") or "A4"),
                cover=bool(params.get("cover")),
                toc=bool(params.get("toc")),
                base_dir=base_dir,
                theme=theme,
                cover_data=params.get("cover_data"),
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
