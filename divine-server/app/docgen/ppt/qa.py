"""PPT 产物质检（docs/fix/001-ppt-empty-slides-20260906.md §4.3）：
重开自检 + 内容版式空页检测，失败不再静默报"PPT 生成完成"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .normalize import check_empty_pages


def verify_pptx(path: Path) -> list[str]:
    """重开自检：产物文件必须能被 python-pptx 正常打开。"""
    try:
        from pptx import Presentation

        presentation = Presentation(str(path))
        if not len(presentation.slides):
            return ["重开后演示文稿没有任何页面"]
    except Exception as exc:  # noqa: BLE001 — 重开失败即产物不可交付
        return [f"产物重开失败（可能已损坏）: {exc}"]
    return []


def qa_slides(
    path: Path,
    items: list[Any],
    layouts: list[str],
) -> list[str]:
    """渲染后质检：重开自检 + 内容版式空页检测。"""
    warnings = verify_pptx(path)
    warnings.extend(check_empty_pages(items, layouts))
    return warnings
