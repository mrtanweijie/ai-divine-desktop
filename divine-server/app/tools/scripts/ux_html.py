from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".html"):
        cleaned += ".html"
    return cleaned


def derive_title(title: str, content: str) -> str:
    candidate = (title or "").strip()
    if candidate:
        return candidate
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    if match:
        value = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if value:
            return value[:80]
    match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
    if match:
        value = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if value:
            return value[:80]
    return "UX交互原型"


ALLOWED_STYLES = {"Notion", "Linear", "Apple", "PlainText", "Custom"}


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    style = str(params.get("style") or "").strip()
    style_note = str(params.get("style_note") or "").strip()
    content = str(params.get("content") or "").strip()
    if style not in ALLOWED_STYLES:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "style 必须由用户明确选择：Notion/Linear/Apple/PlainText/Custom",
                },
                ensure_ascii=False,
            )
        )
        return
    if style == "Custom" and not style_note:
        print(
            json.dumps(
                {"success": False, "message": "选择 Custom 时必须提供 style_note 描述用户偏好"},
                ensure_ascii=False,
            )
        )
        return
    if not content:
        print(
            json.dumps(
                {"success": False, "message": "content 不能为空，请传入完整 HTML 页面源码"},
                ensure_ascii=False,
            )
        )
        return
    if "<html" not in content.lower() and "<!doctype html" not in content.lower():
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "content 必须是完整 HTML 页面源码，应包含 DOCTYPE 或 <html>；不要传入需求文档正文",
                },
                ensure_ascii=False,
            )
        )
        return

    title = derive_title(str(params.get("title") or ""), content)
    output_dir = output_root / "html"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace)
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
    output_path = output_dir / safe_name(title, "UX交互原型")
    output_path.write_text(content, encoding="utf-8")

    print(
        json.dumps(
            {
                "success": True,
                "message": "UX 交互 HTML 页面已生成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {
                    "title": title,
                    "style": style,
                    "size": output_path.stat().st_size,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M"),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
