from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svg_common import (
    build_description,
    parse_svg,
    strip_fence,
)


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}

    raw_path = str(params.get("file_path") or "").strip()
    if not raw_path:
        print(
            json.dumps(
                {"success": False, "message": "缺少 file_path，请传当前 SVG 文件路径"},
                ensure_ascii=False,
            )
        )
        return
    source = Path(raw_path)
    if not source.is_absolute():
        source = workspace / source
    source = source.resolve()
    if not source.is_file():
        print(json.dumps({"success": False, "message": f"文件不存在: {source}"}))
        return
    if source.suffix.lower() != ".svg":
        print(json.dumps({"success": False, "message": "file_path 必须是 .svg 文件"}))
        return

    try:
        old_content = source.read_text(encoding="utf-8")
        parse_svg(old_content)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"当前 SVG 文件解析失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    content = strip_fence(params.get("content") or "")
    if not content:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "content 不能为空，请传入完整更新后的 SVG 源码",
                },
                ensure_ascii=False,
            )
        )
        return
    if len(content) > 60_000:
        print(
            json.dumps(
                {"success": False, "message": "SVG 源码超过 60000 字符限制"},
                ensure_ascii=False,
            )
        )
        return
    try:
        parse_svg(content)  # 校验 SVG 合法性（解析结果无需使用）
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"SVG 解析失败，content 必须是合法 SVG 源码: {exc}",
                },
                ensure_ascii=False,
            )
        )
        return

    source.write_text(content + "\n", encoding="utf-8")
    _, data = build_description(source, content)
    print(
        json.dumps(
            {
                "success": True,
                "message": "SVG 已更新",
                "file_name": source.name,
                "filepath": str(source),
                "data": {
                    **data,
                    "size": source.stat().st_size,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
