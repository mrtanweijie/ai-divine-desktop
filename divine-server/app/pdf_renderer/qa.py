"""渲染后质检（pymupdf）：空白页 / 文本越界 / 超密检测 + 一次修复重渲。

WeasyPrint 正常排版不会越界，越界几乎都来自不可断行的长 token
（URL、代码、连续英文）；对应修复为注入 overflow-wrap CSS 后重渲一轮。
空白页无法安全地自动修复（可能来自封面分页约定），只上报。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("divine.pdf")

# 单页文本字符数上限：A4 10.5pt/1.85 行高正常容量约 2500 字，
# 超过该值基本意味着字号异常或内容挤压
_MAX_PAGE_CHARS = 6000
# 页面边界容差（pt）
_BOUND_EPS = 2.0

# 可自动修复的问题类型（触发 overflow-wrap 修复重渲）
_FIXABLE_TYPES = frozenset({"text_overflow", "dense_page"})

_AVAILABLE: bool | None = None


def qa_available() -> bool:
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import pymupdf  # noqa: F401

            _AVAILABLE = True
        except Exception:
            _AVAILABLE = False
            logger.warning("pymupdf 不可用，渲染后质检已跳过")
    return _AVAILABLE


def overflow_fix_css() -> str:
    """修复重渲时注入的 CSS：允许长 token 断行，防止越界。"""
    return (
        "\n/* pdf-qa overflow fix */\n"
        "body, p, li, td, th, pre, code, h1, h2, h3, h4, h5, h6 "
        "{ overflow-wrap: break-word; word-break: break-word; }\n"
        "pre { white-space: pre-wrap; }\n"
    )


def _block_out_of_bounds(x0: float, x1: float, rect: Any) -> bool:
    """文本块水平越界判定（纯函数，便于单测）。

    仅检测水平越界：正文垂直方向总会分页，纵向超出页底基本都是
    margin box（页脚页码）在零边距封面页上的固有表现，属于渲染器
    特性而非内容问题。
    """
    return x1 > rect.x1 + _BOUND_EPS or x0 < rect.x0 - _BOUND_EPS


def inspect_pdf(pdf_path: Path) -> dict[str, Any]:
    """检查渲染产物，返回 {passed, issues, pages, available}。"""
    if not qa_available():
        return {"passed": True, "issues": [], "available": False}
    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
    except Exception as exc:
        logger.warning("质检打开 PDF 失败: %s", exc)
        return {
            "passed": True,
            "issues": [{"type": "inspect_failed", "detail": str(exc)}],
            "available": False,
        }
    issues: list[dict[str, Any]] = []
    page_count = 0
    try:
        page_count = doc.page_count
        for index, page in enumerate(doc):
            page_no = index + 1
            text = page.get_text("text").strip()
            has_images = bool(page.get_images(full=True))
            has_drawings = bool(page.get_drawings())
            if not text and not has_images and not has_drawings:
                issues.append({"type": "blank_page", "page": page_no})
                continue
            if len(text) > _MAX_PAGE_CHARS:
                issues.append(
                    {"type": "dense_page", "page": page_no, "chars": len(text)}
                )
            rect = page.rect
            for block in page.get_text("blocks"):
                if _block_out_of_bounds(block[0], block[2], rect):
                    snippet = " ".join(str(block[4]).split())[:40]
                    issues.append(
                        {
                            "type": "text_overflow",
                            "page": page_no,
                            "detail": snippet,
                        }
                    )
                    break  # 每页报告一处即可
    finally:
        doc.close()
    return {
        "passed": not issues,
        "issues": issues,
        "pages": page_count,
        "available": True,
    }


def render_with_qa(
    render: Callable[..., dict[str, Any]],
    output: Path,
    base_kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行渲染 + 质检 + 一次修复重渲。

    render 必须接受 extra_css 关键字参数。返回 (render_meta, qa_report)。
    """
    meta = render(**base_kwargs)
    qa = inspect_pdf(output)
    if not qa.get("available") or qa["passed"]:
        return meta, qa
    if not any(
        issue.get("type") in _FIXABLE_TYPES for issue in qa["issues"]
    ):
        # 空白页等不可修复问题：仅上报
        return meta, qa
    first_pass = qa
    retry_kwargs = {**base_kwargs, "extra_css": overflow_fix_css()}
    try:
        meta = render(**retry_kwargs)
        qa = {
            **inspect_pdf(output),
            "fixed": True,
            "first_pass_issues": first_pass["issues"],
        }
    except Exception as exc:
        logger.warning("质检修复重渲失败，保留首渲结果: %s", exc)
        qa = {**first_pass, "fix_failed": True}
    return meta, qa
