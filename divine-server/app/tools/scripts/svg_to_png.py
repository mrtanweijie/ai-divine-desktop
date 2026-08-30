from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svg_common import parse_svg, render_svg_to_png, svg_metadata  # noqa: E402


def _resolve_source(workspace: Path, raw_path: str) -> Path:
    if not raw_path:
        raise ValueError("缺少 file_path，请传 SVG 文件路径")
    source = Path(raw_path)
    if not source.is_absolute():
        source = workspace / source
    source = source.resolve()
    if not source.is_file():
        raise ValueError(f"文件不存在: {source}")
    if source.suffix.lower() != ".svg":
        raise ValueError("file_path 必须是 .svg 文件")
    return source


def _resolve_output(
    workspace: Path, output_root: Path, source: Path, raw_output: str
) -> Path:
    raw_output = (raw_output or "").strip()
    if not raw_output:
        return output_root / "svg" / f"{source.stem}.png"
    output = Path(raw_output)
    if not output.is_absolute():
        output = workspace / output
    output = output.resolve()
    if output.is_dir() or raw_output.endswith(("/", "\\")):
        output = output / f"{source.stem}.png"
    if output.suffix.lower() != ".png":
        output = output.with_suffix(".png")
    return output




def _apply_size(output: Path, width: int | None, height: int | None) -> tuple[int, int]:
    from PIL import Image

    with Image.open(output) as image:
        image.load()
        rgba = image.convert("RGBA")
        target_width = width
        target_height = height
        if target_width and not target_height:
            target_height = max(
                1, round(rgba.height * target_width / max(1, rgba.width))
            )
        elif target_height and not target_width:
            target_width = max(
                1, round(rgba.width * target_height / max(1, rgba.height))
            )
        if target_width and target_height:
            rgba = rgba.resize(
                (max(1, int(target_width)), max(1, int(target_height))),
                Image.LANCZOS,
            )
        rgba.save(output, format="PNG")
        return rgba.size


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    try:
        source = _resolve_source(workspace, str(params.get("file_path") or ""))
    except ValueError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
        return

    width = params.get("width")
    height = params.get("height")
    try:
        width = int(width) if width is not None else None
        height = int(height) if height is not None else None
    except (TypeError, ValueError):
        print(
            json.dumps(
                {"success": False, "message": "width/height 必须是整数"},
                ensure_ascii=False,
            )
        )
        return
    if (width is not None and width <= 0) or (height is not None and height <= 0):
        print(
            json.dumps(
                {"success": False, "message": "width/height 必须大于 0"},
                ensure_ascii=False,
            )
        )
        return

    try:
        output = _resolve_output(
            workspace, output_root, source, str(params.get("output_path") or "")
        )
    except ValueError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
        return
    output.parent.mkdir(parents=True, exist_ok=True)

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

    ok, renderer = render_svg_to_png(
        source, output,
        max_dim=max(
            width or 0,
            height or 0,
            int(meta.get("width") or 0),
            int(meta.get("height") or 0),
            1024,
        ),
    )
    if not ok:
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

    try:
        final_size = _apply_size(output, width, height)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"PNG 尺寸处理失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {
                "success": True,
                "message": "SVG 已导出为 PNG",
                "file_name": output.name,
                "filepath": str(output),
                "data": {
                    "renderer": renderer,
                    "width": final_size[0],
                    "height": final_size[1],
                    "source_file": source.name,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
