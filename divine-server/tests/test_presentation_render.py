"""presentation 脚本渲染验证：14 种版式 / 原生图表 / 表格 / 图片 / 兜底逻辑。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "presentation.py"


def _run(payload: dict, tmp_path: Path) -> dict:
    body = {
        "workspace": str(tmp_path / "workspace"),
        "output_dir": str(tmp_path / "output"),
        "params": payload,
    }
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(body, ensure_ascii=False),
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def _all_layout_slides() -> list[dict]:
    return [
        {"layout": "toc", "points": ["市场洞察", "增长引擎", "产品路线",
                                      "组织保障", "财务规划", "风险与应对"]},
        {"layout": "section", "heading": "产品路线"},
        {"layout": "two_col", "heading": "智能体平台 2.0",
         "points": ["多模态理解升级", "零代码编排引擎", "内置行业模板"]},
        {"layout": "cards", "heading": "三大增长引擎",
         "points": ["企业客户|深耕 KA 标杆", "生态合作|覆盖 200 城", "智能提效|人效 +40%"]},
        {"layout": "timeline", "heading": "2026 关键里程碑",
         "points": ["Q1|联盟成立", "Q2|扩编完成", "Q3|新品发布", "Q4|年度复盘"]},
        {"layout": "columns", "heading": "三维度展开",
         "points": ["产品力", "渠道力", "运营力"]},
        {"layout": "compare", "heading": "增长路径对比",
         "left": {"title": "自建团队", "points": ["可控性强", "周期 6 个月"]},
         "right": {"title": "生态合作", "points": ["起量快", "周期 2 个月"]}},
        {"layout": "kpi", "heading": "上半年核心指标",
         "points": ["1,668|营收（万元）|同比 +38%", "1,240|客户数|+52%",
                    "91%|复购率|+6pt", "68|NPS|+12"]},
        {"layout": "quote", "heading": "增长的本质是构建可复用的价值网络",
         "subtitle": "2026 增长战略纲要"},
        {"layout": "table", "heading": "区域销售明细",
         "table": {"columns": ["区域", "营收", "同比"],
                   "rows": [["华东", "634", "+45%"], ["华北", "428", "+32%"]]}},
        {"layout": "chart", "heading": "季度营收趋势",
         "chart": {"type": "column", "categories": ["Q1", "Q2", "Q3", "Q4"],
                   "series": [{"name": "营收", "values": [312, 444, 386, 528]}]},
         "points": ["Q2 环比 +42%", "Q4 冲刺 528 万"]},
        {"layout": "bullets", "heading": "风险与应对",
         "points": ["市场波动：多元化布局", "供给不足：提前锁产能"]},
        {"layout": "end", "heading": "谢谢观看", "subtitle": "让每一页都有设计感"},
    ]


def test_all_layouts_render(tmp_path):
    result = _run({"title": "2026 增长战略规划", "theme": "universal",
                   "slides": _all_layout_slides()}, tmp_path)
    assert result["success"] is True, result
    output = Path(result["filepath"])
    assert output.is_file() and output.stat().st_size > 0

    prs = Presentation(str(output))
    # 封面 + 12 内容页 + 结尾页
    assert len(prs.slides) == 14

    all_shapes = [shape for slide in prs.slides for shape in slide.shapes]
    assert any(shape.has_chart for shape in all_shapes), "原生图表缺失"
    assert any(shape.has_table for shape in all_shapes), "表格缺失"


def test_chart_slide_has_editable_chart(tmp_path):
    result = _run({"title": "图表验证",
                   "slides": [{"layout": "chart", "heading": "趋势",
                               "chart": {"type": "pie",
                                         "categories": ["华东", "华北", "华南"],
                                         "series": [{"name": "占比",
                                                     "values": [38, 26, 21]}]}}]},
                  tmp_path)
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])
    charts = [shape.chart for slide in prs.slides for shape in slide.shapes
              if shape.has_chart]
    assert len(charts) == 1
    plot = charts[0].plots[0]
    assert len(list(plot.categories)) == 3
    assert len(list(charts[0].series)) == 1


def test_chart_unsupported_type_fails_gracefully(tmp_path):
    result = _run({"title": "非法图表",
                   "slides": [{"layout": "chart", "heading": "桑基图",
                               "chart": {"type": "sankey", "categories": ["A"],
                                         "series": [{"name": "s", "values": [1]}]}}]},
                  tmp_path)
    assert result["success"] is False
    assert "generate_chart" in result["message"]


def test_chart_over_limit_fails_gracefully(tmp_path):
    values = list(range(20))
    result = _run({"title": "超限图表",
                   "slides": [{"layout": "chart", "heading": "过多数据点",
                               "chart": {"type": "bar",
                                         "categories": [f"c{i}" for i in values],
                                         "series": [{"name": "s",
                                                     "values": values}]}}]},
                  tmp_path)
    assert result["success"] is False
    assert "聚合" in result["message"]


def test_two_col_with_local_image(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    image_path = workspace / "product.png"
    Image.new("RGB", (800, 600), color=(37, 99, 235)).save(image_path)
    result = _run({"title": "图文页",
                   "slides": [{"layout": "two_col", "heading": "产品发布",
                               "points": ["要点一"],
                               "image": {"path": "product.png",
                                         "caption": "产品主视觉"}}]},
                  tmp_path)
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])
    pictures = [shape for slide in prs.slides for shape in slide.shapes
                if shape.shape_type is not None and str(shape.shape_type).startswith("PICTURE")]
    assert pictures, "本地图片未插入"


def test_svg_image_converted_to_picture(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120">'
        '<rect width="200" height="120" fill="#7C3AED"/></svg>',
        encoding="utf-8",
    )
    result = _run({"title": "SVG 配图",
                   "slides": [{"layout": "two_col", "heading": "品牌页",
                               "points": ["品牌资产"],
                               "image": {"path": "logo.svg"}}]},
                  tmp_path)
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])
    pictures = [shape for slide in prs.slides for shape in slide.shapes
                if shape.shape_type is not None and str(shape.shape_type).startswith("PICTURE")]
    assert pictures, "SVG 未转 PNG 插入"


def test_image_outside_workspace_falls_back_to_placeholder(tmp_path):
    outside = tmp_path / "outside.png"
    from PIL import Image

    Image.new("RGB", (100, 100), color=(0, 0, 0)).save(outside)
    result = _run({"title": "越界图片",
                   "slides": [{"layout": "two_col", "heading": "安全校验",
                               "points": ["要点"],
                               "image": {"path": str(outside)}}]},
                  tmp_path)
    # 越界路径不应导致失败，降级为占位块
    assert result["success"] is True, result
    prs = Presentation(result["filepath"])
    pictures = [shape for slide in prs.slides for shape in slide.shapes
                if shape.shape_type is not None and str(shape.shape_type).startswith("PICTURE")]
    assert not pictures, "越界图片不应被插入"


def test_auto_end_slide(tmp_path):
    result = _run({"title": "自动结尾",
                   "slides": [{"layout": "bullets", "heading": "要点",
                               "points": ["一", "二"]}]}, tmp_path)
    assert result["success"] is True
    assert result["data"]["slides"] == 3  # 封面 + 内容 + 自动结尾

    result2 = _run({"title": "显式结尾",
                    "slides": [{"layout": "bullets", "heading": "要点",
                                "points": ["一"]},
                               {"layout": "end", "heading": "再见"}]}, tmp_path)
    assert result2["success"] is True
    assert result2["data"]["slides"] == 3  # 封面 + 内容 + 显式结尾，不重复


def test_textfit_estimation():
    from app.ppt_renderer.textfit import pick_size, text_em_width, wrapped_lines

    assert text_em_width("中文") == 2.0
    assert text_em_width("ab") == 1.1
    assert wrapped_lines("一" * 20, 5.0, 20) == 2  # 每行 18 字，20 字折 2 行
    assert wrapped_lines("hello world", 5.0, 20) == 1
    long_text = "要点" * 30
    short_text = "短要点"
    assert pick_size(long_text, 6.0, 0.8, [20, 18, 16, 14]) < \
        pick_size(short_text, 6.0, 0.8, [20, 18, 16, 14])


def test_guess_layout():
    from app.ppt_renderer.layouts import guess_layout

    assert guess_layout({"heading": "目录"}) == "toc"
    assert guess_layout({"heading": "2026 路线图"}) == "timeline"
    assert guess_layout({"heading": "引擎", "points": list("abcde")}) == "cards"
    assert guess_layout({"heading": "引擎", "points": list("abc")}) == "columns"
    assert guess_layout({"heading": "总结", "body": "长文本"}) == "bullets"
