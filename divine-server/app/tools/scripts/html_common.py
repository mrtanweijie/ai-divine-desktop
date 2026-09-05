"""html_common 工具：按用户要求原样保存 HTML，不注入风格 token 基座。

与 html_generate 的分工：
- html_generate —— 通用 HTML 页面，注入设计 token 基座并做静态校验；
- html_common   —— 用户提供了自己的 HTML（自带简历模板、自定义版式）或明确
  要求原样输出时使用：不注入基座、不做简历拦截，内容一字不改直接落盘。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    content = str(params.get("content") or "").strip()

    if not content:
        print(
            json.dumps(
                {"success": False, "message": "content 不能为空，请传入完整 HTML 页面源码"},
                ensure_ascii=False,
            )
        )
        return
    lowered = content.lower()
    if "<html" not in lowered and "<!doctype html" not in lowered:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "content 必须是完整 HTML 页面源码，应包含 DOCTYPE 或 <html>",
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return

    # 标题仅用于命名：从 params.title、<title> 或首个 <h1> 推导
    title = str(params.get("title") or "").strip()
    if not title:
        import re

        m = re.search(r"<title>([^<]*)</title>", content, re.IGNORECASE)
        title = m.group(1).strip() if m else ""
    if not title:
        m = re.search(r"<h1[^>]*>([^<]*)</h1>", content, re.IGNORECASE)
        title = m.group(1).strip() if m else ""
    if not title:
        title = "页面"

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

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "页面", ".html")
    output_path.write_text(content, encoding="utf-8")

    print(
        json.dumps(
            {
                "success": True,
                "message": "HTML 已按原样保存（未注入风格基座，内容一字未改）",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {"title": title, "verbatim": True},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
