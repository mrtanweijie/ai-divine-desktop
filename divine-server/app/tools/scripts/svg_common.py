from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SVG_NS = "http://www.w3.org/2000/svg"

_ATTR_KEYS = (
    "id",
    "class",
    "transform",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "d",
    "points",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "width",
    "height",
    "viewBox",
    "font-size",
    "font-family",
    "font-weight",
    "text-anchor",
    "href",
)

_SKIP_TAGS = {"defs", "style", "metadata"}
_MAX_ELEMENTS = 80


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def strip_fence(content: str) -> str:
    lines = content.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_svg(content: str):
    root = ET.fromstring(content)
    if local_name(root.tag) != "svg":
        raise ValueError("内容不是 SVG：根元素必须是 <svg>")
    return root


def parse_length(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:px)?\s*$", str(value))
    if not match:
        return None
    return float(match.group(1))


def svg_metadata(root: Any) -> dict[str, Any]:
    width = parse_length(root.attrib.get("width"))
    height = parse_length(root.attrib.get("height"))
    view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox") or ""
    if view_box:
        parts = view_box.split()
        if len(parts) == 4:
            if width is None:
                width = parse_length(parts[2])
            if height is None:
                height = parse_length(parts[3])
    return {
        "width": width,
        "height": height,
        "viewBox": view_box.strip(),
    }


def _element_text(elem: Any) -> str:
    pieces: list[str] = []
    if elem.text and elem.text.strip():
        pieces.append(elem.text.strip())
    for child in elem:
        if local_name(child.tag) in ("tspan", "textPath"):
            if child.text and child.text.strip():
                pieces.append(child.text.strip())
    return " ".join(pieces)[:60]


def collect_elements(root: Any, limit: int = _MAX_ELEMENTS) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for elem in root.iter():
        tag = local_name(elem.tag)
        if tag in _SKIP_TAGS and not elem.attrib.get("id"):
            continue
        attrs = {
            key: str(elem.attrib[key])
            for key in _ATTR_KEYS
            if key in elem.attrib
        }
        entry: dict[str, Any] = {
            "tag": tag,
            "attrs": attrs,
        }
        if tag in ("text", "tspan", "textPath") and _element_text(elem):
            entry["text"] = _element_text(elem)
        result.append(entry)
        if len(result) >= limit:
            break
    return result


def format_attrs(attrs: dict[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in attrs.items())


def build_description(
    source: Path, content: str, include_source: bool = False
) -> tuple[str, dict[str, Any]]:
    root = parse_svg(content)
    meta = svg_metadata(root)
    elements = collect_elements(root)
    ids = [
        str(element["attrs"].get("id"))
        for element in elements
        if element["attrs"].get("id")
    ]
    lines = [
        f"SVG 文件: {source.name}",
        f"画布: width={meta['width']}, height={meta['height']}, "
        f"viewBox={meta['viewBox'] or '未设置'}",
        f"元素数量: {len(elements)}，带 id 元素: {len(ids)}",
    ]
    if ids:
        lines.append("关键 id: " + ", ".join(ids))
    lines.append("元素清单:")
    for element in elements:
        attrs = format_attrs(element["attrs"])
        label = f"- <{element['tag']}>"
        if attrs:
            label += f" {attrs}"
        if element.get("text"):
            label += f" text=\"{element['text']}\""
        lines.append(label)
    description = "\n".join(lines)
    if include_source:
        description += "\n\n完整源码:\n" + content
    data = {
        **meta,
        "element_count": len(elements),
        "id_count": len(ids),
        "ids": ids,
        "elements": elements,
    }
    return description, data


def safe_name(name: str, fallback: str, suffix: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", str(name or "")).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.lower().endswith(suffix.lower()):
        cleaned += suffix
    return cleaned


# ----------------------------------------------------------------------
# SVG → PNG 渲染链（resvg → cairosvg → svglib → qlmanage）
# 供 svg_to_png 与 presentation（复杂图表 SVG 兜底）共用，同进程调用。

import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402


def _render_with_resvg(source: Path, output: Path) -> bool:
    try:
        import resvg_py

        png_bytes = resvg_py.svg_to_bytes(svg_string=source.read_text(encoding="utf-8"))
        output.write_bytes(png_bytes)
        return True
    except Exception:  # noqa: BLE001
        return False


def _render_with_cairosvg(source: Path, output: Path) -> bool:
    try:
        import cairosvg

        cairosvg.svg2png(url=str(source), write_to=str(output))
        return True
    except Exception:  # noqa: BLE001
        return False


def _render_with_svglib(source: Path, output: Path) -> bool:
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM

        drawing = svg2rlg(str(source))
        renderPM.drawToFile(drawing, str(output), fmt="PNG", dpi=96)
        return True
    except Exception:  # noqa: BLE001
        return False


def _render_with_qlmanage(source: Path, output: Path, max_dim: int) -> bool:
    if sys.platform != "darwin":
        return False
    qlmanage = shutil.which("qlmanage")
    if not qlmanage:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="svg_to_png_") as tmp:
            completed = subprocess.run(
                [qlmanage, "-t", "-s", str(max(1, int(max_dim))), "-o", tmp,
                 str(source)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if completed.returncode != 0:
                return False
            rendered = Path(tmp) / f"{source.name}.png"
            if not rendered.is_file():
                return False
            shutil.move(str(rendered), str(output))
        return True
    except Exception:  # noqa: BLE001
        return False


def render_svg_to_png(source: Path, output: Path, max_dim: int = 2048) -> tuple[bool, str]:
    """把 SVG 渲染为 PNG，返回 (是否成功, 渲染器名)。"""
    for renderer_name, renderer in (
        ("resvg_py", _render_with_resvg),
        ("cairosvg", _render_with_cairosvg),
        ("svglib", _render_with_svglib),
        ("qlmanage", lambda src, out: _render_with_qlmanage(src, out, max_dim)),
    ):
        try:
            if renderer(source, output):
                return True, renderer_name
        except Exception:  # noqa: BLE001
            continue
    return False, ""
