from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svg_common import (
    build_description,
    parse_svg,
    safe_name,
    strip_fence,
)


def _resolve_output_dir(workspace: Path, output_root: Path, raw_path: str) -> Path:
    output_dir = output_root / "svg"
    raw_path = (raw_path or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace.resolve())
        except ValueError:
            raise ValueError(f"保存路径越界: {output_dir}")
    return output_dir


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    content = strip_fence(params.get("content") or "")
    if not content:
        print(
            json.dumps(
                {"success": False, "message": "content 不能为空，请传入完整 SVG 源码"},
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
        root = parse_svg(content)
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

    title = str(params.get("title") or "SVG图形").strip()
    file_name = str(params.get("file_name") or title).strip()
    raw_path = str(params.get("path") or "").strip()
    try:
        output_dir = _resolve_output_dir(workspace, output_root, raw_path)
    except ValueError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
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
    output_path = output_dir / safe_name(file_name, "SVG图形", ".svg")
    output_path.write_text(content + "\n", encoding="utf-8")

    _, data = build_description(output_path, content)
    print(
        json.dumps(
            {
                "success": True,
                "message": "SVG 已生成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {
                    **data,
                    "size": output_path.stat().st_size,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M"),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
