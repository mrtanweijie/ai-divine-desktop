"""渲染后质检（qa.py）测试。"""

import pymupdf
import pytest

from app.docgen.pdf.renderer import qa


def _make_pdf(path, *, pages: list[str]) -> None:
    """生成测试 PDF：每个元素描述一页行为。

    - "text"：正常文本页
    - "blank"：空白页
    - "overflow"：文本块越过页面右边界（长 token 不断行）
    - "dense"：超过密度阈值的文本页
    """
    doc = pymupdf.open()
    for kind in pages:
        page = doc.new_page()
        if kind == "text":
            page.insert_text((72, 100), "正常内容 正文")
        elif kind == "overflow":
            page.insert_text((600, 100), "w" * 30, fontsize=10)
        elif kind == "dense":
            page.insert_textbox(
                pymupdf.Rect(50, 50, 545, 790),
                "字" * (qa._MAX_PAGE_CHARS + 500),
                fontsize=6,
            )
    doc.save(str(path))
    doc.close()


def test_qa_available():
    assert qa.qa_available() is True


def test_inspect_clean_pdf(tmp_path):
    pdf = tmp_path / "clean.pdf"
    _make_pdf(pdf, pages=["text", "text"])
    report = qa.inspect_pdf(pdf)
    assert report["available"] is True
    assert report["passed"] is True
    assert report["issues"] == []
    assert report["pages"] == 2


def test_inspect_blank_page(tmp_path):
    pdf = tmp_path / "blank.pdf"
    _make_pdf(pdf, pages=["text", "blank", "text"])
    report = qa.inspect_pdf(pdf)
    assert report["passed"] is False
    blanks = [i for i in report["issues"] if i["type"] == "blank_page"]
    assert blanks == [{"type": "blank_page", "page": 2}]


def test_block_out_of_bounds_pure_logic():
    import pymupdf as pm

    rect = pm.Rect(0, 0, 595, 842)
    assert qa._block_out_of_bounds(60, 700, rect) is True  # 右侧越界
    assert qa._block_out_of_bounds(-10, 200, rect) is True  # 左侧越界
    assert qa._block_out_of_bounds(60, 500, rect) is False
    assert qa._block_out_of_bounds(0, 596.5, rect) is False  # 2pt 容差内


def test_inspect_ignores_vertical_overflow_of_margin_boxes(tmp_path):
    """页脚页码在零边距封面页上会纵向超出页底（渲染器特性），不应误报。"""
    pdf = tmp_path / "footer.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((288, 836), "1 / 2", fontsize=8.5)  # 纵向贴边/略超出
    doc.save(str(pdf))
    doc.close()
    report = qa.inspect_pdf(pdf)
    assert report["passed"] is True
    assert report["issues"] == []


def test_inspect_text_overflow(tmp_path):
    """水平越界经 _block_out_of_bounds 纯逻辑覆盖（pymupdf 对越界块坐标
    会截断到页边，真实 PDF 上难以稳定复现 >2pt 的水平越界）。"""
    pdf = tmp_path / "overflow.pdf"
    _make_pdf(pdf, pages=["text"])
    report = qa.inspect_pdf(pdf)
    assert report["available"] is True
    # 正常页不应被误判
    assert not any(i["type"] == "text_overflow" for i in report["issues"])


def test_inspect_dense_page(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _make_pdf(pdf, pages=["dense"])
    report = qa.inspect_pdf(pdf)
    assert report["passed"] is False
    dense = [i for i in report["issues"] if i["type"] == "dense_page"]
    assert dense and dense[0]["chars"] > qa._MAX_PAGE_CHARS


def test_inspect_missing_file_reports_unavailable():
    report = qa.inspect_pdf("/nonexistent/never.pdf")
    assert report["available"] is False
    assert report["passed"] is True


def test_render_with_qa_no_issues_single_render(tmp_path, monkeypatch):
    calls = []

    def render(**kwargs):
        calls.append(kwargs)
        return {"renderer": "fake"}

    monkeypatch.setattr(
        qa, "inspect_pdf", lambda _: {"passed": True, "issues": [], "available": True}
    )
    meta, report = qa.render_with_qa(render, tmp_path / "out.pdf", {"a": 1})
    assert calls == [{"a": 1}]
    assert meta == {"renderer": "fake"}
    assert report["passed"] is True


def test_render_with_qa_fixable_issue_rerenders(tmp_path, monkeypatch):
    calls = []
    reports = iter(
        [
            {
                "passed": False,
                "available": True,
                "issues": [{"type": "text_overflow", "page": 3}],
            },
            {"passed": True, "available": True, "issues": []},
        ]
    )

    def render(**kwargs):
        calls.append(kwargs)
        return {"renderer": "fake"}

    monkeypatch.setattr(qa, "inspect_pdf", lambda _: next(reports))
    meta, report = qa.render_with_qa(render, tmp_path / "out.pdf", {"a": 1})
    assert len(calls) == 2
    assert qa.overflow_fix_css() in calls[1]["extra_css"]
    assert report["fixed"] is True
    assert report["first_pass_issues"] == [
        {"type": "text_overflow", "page": 3}
    ]


def test_render_with_qa_blank_page_not_rerendered(tmp_path, monkeypatch):
    calls = []

    def render(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(
        qa,
        "inspect_pdf",
        lambda _: {
            "passed": False,
            "available": True,
            "issues": [{"type": "blank_page", "page": 2}],
        },
    )
    _, report = qa.render_with_qa(render, tmp_path / "out.pdf", {})
    assert len(calls) == 1  # 空白页只上报，不重渲
    assert report["passed"] is False


def test_render_with_qa_unavailable_skips(tmp_path, monkeypatch):
    calls = []

    def render(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(
        qa, "inspect_pdf", lambda _: {"passed": True, "issues": [], "available": False}
    )
    qa.render_with_qa(render, tmp_path / "out.pdf", {})
    assert len(calls) == 1


def test_overflow_fix_css_targets_long_tokens():
    css = qa.overflow_fix_css()
    assert "overflow-wrap: break-word" in css
    assert "pre-wrap" in css
