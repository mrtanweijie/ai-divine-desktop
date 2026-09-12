"""pptx 转 PNG（agent 工具脚本）：把演示文稿每页渲染成 PNG 文件落盘。

stdin/stdout JSON 约定与其它工具脚本一致：
入参 {"workspace": str, "output_dir": str, "params": {...}}
出参 {"success": bool, "message": str, "filepath": str, "data": {...}}

params:
  file_path   必填，pptx/ppsx 路径（workspace 相对或绝对）
  output_path 可选，输出目录（默认 output_dir/presentations/<stem>-png）
  scale       可选，渲染倍率（1.0 = 96dpi），默认 1.5
  page        可选，1 基页码；只导出该页
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.ppt.pptx_to_png import (  # noqa: E402
    MAX_PPTX_PREVIEW_PAGES,
    PPTX_RENDER_SCALE,
    render_pptx_to_files,
)

_SOURCE_SUFFIXES = (".pptx", ".ppsx")


def _fail(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


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


def _resolve_source(workspace: Path, raw: str) -> Path:
    if not raw:
        raise ValueError("缺少 file_path，请传 pptx 文件路径")
    source = _resolve_inside(workspace, raw)
    if source is None and raw.startswith("/"):
        # 允许读取应用输出目录里的产物（与 presentation/pdf 工具一致）
        from app.config import output_dir

        source = _resolve_inside(output_dir().resolve(), raw)
    if source is None:
        raise ValueError(f"路径越界，只能读取 workspace 或输出目录内的文件: {raw}")
    if not source.is_file():
        raise ValueError(f"文件不存在: {source}")
    if source.suffix.lower() not in _SOURCE_SUFFIXES:
        raise ValueError("file_path 必须是 .pptx / .ppsx 文件")
    return source


def _resolve_output_dir(workspace: Path, output_root: Path,
                        source: Path, raw: str) -> Path:
    raw = (raw or "").strip()
    if not raw:
        return output_root / "presentations" / f"{source.stem}-png"
    # 防御性剥离文件名：output_path 语义是目录，多页输出天然是目录
    if raw.lower().endswith(".png"):
        raw = str(Path(raw).parent)
    inside = _resolve_inside(workspace, raw)
    if inside is None and raw.startswith("/"):
        inside = _resolve_inside(output_root, raw)
    if inside is None:
        raise ValueError(f"输出路径越界，必须落在 workspace 或输出目录内: {raw}")
    return inside


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    try:
        source = _resolve_source(workspace, str(params.get("file_path") or ""))
    except ValueError as exc:
        _fail(str(exc))
        return

    raw_scale = params.get("scale")
    try:
        scale = float(raw_scale) if raw_scale not in (None, "") else PPTX_RENDER_SCALE
    except (TypeError, ValueError):
        _fail("scale 必须是数字")
        return
    if not 0.5 <= scale <= 3.0:
        _fail("scale 需在 0.5 - 3.0 之间")
        return

    page = params.get("page")
    if page not in (None, ""):
        try:
            page = int(page)
        except (TypeError, ValueError):
            _fail("page 必须是整数页码")
            return
    else:
        page = None

    try:
        outdir = _resolve_output_dir(workspace, output_root, source,
                                     str(params.get("output_path") or ""))
    except ValueError as exc:
        _fail(str(exc))
        return

    try:
        outputs = render_pptx_to_files(source, outdir, scale=scale, page=page)
    except Exception as exc:  # noqa: BLE001
        _fail(f"PPT 转 PNG 失败: {exc}")
        return

    if not outputs:
        _fail("没有生成任何页面")
        return

    total = len(outputs)
    truncated = total >= MAX_PPTX_PREVIEW_PAGES and page is None
    print(
        json.dumps(
            {
                "success": True,
                "message": f"PPT 已导出为 PNG（{total} 页）",
                "file_name": outputs[0].name,
                "filepath": str(outputs[0]),
                "data": {
                    "renderer": "pillow-shape-redraw",
                    "page_count": total,
                    "truncated": truncated,
                    "scale": scale,
                    "page": page,
                    "output_dir": str(outdir),
                    "pages": [str(p) for p in outputs],
                    "source_file": source.name,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
