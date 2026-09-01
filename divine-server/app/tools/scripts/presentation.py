import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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
    slides = params.get("slides") or []
    theme_id = str(params.get("theme") or params.get("style") or "universal").strip()
    get_ppt_theme(theme_id)  # 未知主题回退默认，不报错
    raw_path = str(params.get("path") or "").strip()

    output_dir = output_root / "presentations"
    if raw_path:
        candidate = _resolve_inside(workspace, raw_path)
        if candidate is None:
            print(json.dumps(
                {"success": False, "message": f"保存路径越界: {raw_path}"},
                ensure_ascii=False,
            ))
            return
        output_dir = candidate
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "演示文稿", ".pptx")

    from pptx import Presentation

    from app.docgen.ppt.renderer import SLIDE_H, SLIDE_W

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    resolve_media = _make_media_resolver(workspace, output_root)
    items = list(slides)
    if items and _is_cover_slide(items[0]):
        cover = dict(items[0])
        cover["layout"] = "cover"
        cover.setdefault("heading", title)
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
        items = items + [{"layout": "end", "heading": "谢谢观看"}]

    # 目录页兜底：未显式给出且内容量足够时，按章节页自动生成（含页码）
    def _is_toc(it: dict) -> bool:
        return (str(it.get("layout") or "").strip().lower() == "toc"
                or "目录" in str(it.get("heading") or ""))

    want_toc = params.get("toc")
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

    cover_items[0]["_pages"] = len(items)
    rendered = 0
    try:
        for item in cover_items + items:
            add_slide(prs, item, theme_id, rendered + 1, resolve_media=resolve_media)
            rendered += 1
    except ValueError as exc:
        print(json.dumps(
            {"success": False, "message": str(exc)},
            ensure_ascii=False,
        ))
        return

    prs.save(output_path)
    from app.docgen.ppt.renderer import PPT_THEMES
    from app.docgen.ppt.renderer.themes import STYLES
    print(json.dumps(
        {
            "success": True,
            "message": "PPT 生成完成",
            "file_name": output_path.name,
            "filepath": str(output_path),
            "data": {
                "theme": theme_id,
                "slides": rendered,
                "toc": toc_inserted,
                "presets": len(PPT_THEMES),
                "styles": sorted(STYLES),
            },
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
