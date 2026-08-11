from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svg_common import build_description, parse_svg


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
        content = source.read_text(encoding="utf-8")
        parse_svg(content)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"SVG 解析失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    include_source = bool(params.get("include_source") or False)
    description, summary = build_description(source, content, include_source)
    print(
        json.dumps(
            {
                "success": True,
                "message": "SVG 结构描述已生成",
                "file_name": source.name,
                "filepath": str(source),
                "content": description,
                "data": summary,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
