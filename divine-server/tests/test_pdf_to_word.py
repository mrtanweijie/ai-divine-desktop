"""pdf_to_word 回归：文本 PDF 转换、扫描件失败语义、外部输入、重名避让。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from docx import Document
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))  # 内置 CID 中文字体


def _make_text_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.setFont("STSong-Light", 12)
    c.drawString(72, 750, "季度经营分析报告")
    c.drawString(72, 720, "第一季度营收 1,200 万元，同比增长 18%。")
    c.drawString(72, 690, "第二季度营收 1,450 万元，环比继续增长。")
    c.showPage()
    c.save()


def _run_script(payload: dict) -> dict:
    script = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "pdf_to_word.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def test_convert_text_pdf_to_docx(tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    pdf = ws_dir / "报告.pdf"
    _make_text_pdf(pdf)

    output = _run_script(
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {"path": str(pdf)},
        }
    )
    assert output["success"] is True
    assert output["filepath"].endswith(".docx")
    assert Path(output["filepath"]).parent == ws_dir / "documents"

    produced = Document(output["filepath"])
    all_text = "\n".join(p.text for p in produced.paragraphs)
    assert "季度经营分析报告" in all_text
    assert "1,450 万元" in all_text
    assert output["data"]["pages"] >= 1
    assert output["data"]["chars"] > 20


def test_convert_external_pdf_writes_into_workspace(tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    external = tmp_path / "Desktop"
    external.mkdir()
    pdf = external / "外部报告.pdf"
    _make_text_pdf(pdf)

    output = _run_script(
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {"path": str(pdf)},
        }
    )
    assert output["success"] is True
    produced = Path(output["filepath"])
    assert produced.parent == ws_dir / "documents"  # 产物落在 workspace
    assert pdf.read_bytes()  # 原 PDF 只读不动


def test_convert_scanned_pdf_fails_with_clear_message(tmp_path):
    """无文本层的 PDF（空页/纯图）→ 明确失败，不产空 docx。"""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    scanned = ws_dir / "扫描件.pdf"
    c = canvas.Canvas(str(scanned))  # 空页面：无任何文本
    c.showPage()
    c.save()

    output = _run_script(
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {"path": str(scanned)},
        }
    )
    assert output["success"] is False
    assert "扫描件" in output["message"] or "文本层" in output["message"]
    assert not (ws_dir / "documents" / "扫描件.docx").exists()


def test_convert_duplicate_titles_get_unique_names(tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    pdf = ws_dir / "报告.pdf"
    _make_text_pdf(pdf)

    first = _run_script(
        {"workspace": str(ws_dir), "output_dir": str(ws_dir), "params": {"path": str(pdf)}}
    )
    second = _run_script(
        {"workspace": str(ws_dir), "output_dir": str(ws_dir), "params": {"path": str(pdf)}}
    )
    assert Path(first["filepath"]).name != Path(second["filepath"]).name  # 重名避让
