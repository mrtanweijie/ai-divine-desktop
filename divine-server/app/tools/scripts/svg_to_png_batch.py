from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svg_common import parse_svg, svg_metadata  # noqa: E402
from svg_to_png import (  # noqa: E402
    _apply_size,
    _render_with_cairosvg,
    _render_with_qlmanage,
    _render_with_resvg,
    _render_with_svglib,
    _resolve_source,
)

DEFAULT_IOS_SIZES = [
    1024,
    180,
    167,
    152,
    120,
    87,
    80,
    76,
    60,
    58,
    40,
    29,
    20,
]
MAX_SIZES = 30


def _render_size(source: Path, output: Path, size: int) -> str:
    if _render_with_resvg(source, output):
        return "resvg_py"
    if _render_with_cairosvg(source, output):
        return "cairosvg"
    if _render_with_svglib(source, output):
        return "svglib"
    if _render_with_qlmanage(source, output, size):
        return "qlmanage"
    return ""


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    try:
        source = _resolve_source(workspace, str(params.get("file_path") or ""))
    except ValueError as exc:
        print(
            json.dumps(
                {"success": False, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return

    raw_sizes = params.get("sizes") or []
    if not raw_sizes:
        sizes = DEFAULT_IOS_SIZES
    else:
        try:
            sizes = [int(size) for size in raw_sizes]
        except (TypeError, ValueError):
            print(
                json.dumps(
                    {"success": False, "message": "sizes 必须是正整数列表"},
                    ensure_ascii=False,
                )
            )
            return
    sizes = [size for size in sizes if size > 0]
    if not sizes:
        print(
            json.dumps(
                {"success": False, "message": "sizes 必须包含大于 0 的尺寸"},
                ensure_ascii=False,
            )
        )
        return
    if len(sizes) > MAX_SIZES:
        sizes = sizes[:MAX_SIZES]

    prefix = str(params.get("prefix") or source.stem).strip() or source.stem
    output_dir = output_root / "svg"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        content = source.read_text(encoding="utf-8")
        root = parse_svg(content)
        meta = svg_metadata(root)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"SVG 解析失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return
    _ = meta

    results: list[dict[str, object]] = []
    success_count = 0
    for size in sizes:
        output = output_dir / f"{prefix}_{size}.png"
        renderer = _render_size(source, output, size)
        if not renderer:
            continue
        try:
            final_size = _apply_size(output, size, size)
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "file_name": output.name,
                    "filepath": str(output),
                    "file_size": None,
                    "success": False,
                    "message": f"尺寸处理失败: {exc}",
                }
            )
            continue
        results.append(
            {
                "file_name": output.name,
                "filepath": str(output),
                "file_size": output.stat().st_size,
                "success": True,
                "width": final_size[0],
                "height": final_size[1],
                "renderer": renderer,
            }
        )
        success_count += 1

    if not results:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        "SVG 转 PNG 失败：当前环境没有可用的转换器。"
                        "可安装 resvg_py/cairosvg/svglib，macOS 需要 qlmanage"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    summary = f"已导出 {success_count} 个 PNG 尺寸"
    primary = results[0]
    content = json.dumps(
        {
            "success": True,
            "message": summary,
            "files": [result["file_name"] for result in results],
        },
        ensure_ascii=False,
    )
    print(
        json.dumps(
            {
                "success": True,
                "message": summary,
                "content": content,
                "file_name": primary["file_name"],
                "filepath": primary["filepath"],
                "data": {"results": results, "summary": summary},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
