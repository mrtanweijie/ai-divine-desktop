"""_parse_grounding 单测：视觉模型回复的坐标解析（离线）。"""

from __future__ import annotations

from app.tools.browser_engine.engine import _parse_grounding

LABELS = ["河", "山", "月"]


def test_parse_plain_json():
    text = '[{"label": "河", "x": 165, "y": 95}, {"label": "山", "x": 55, "y": 45}, {"label": "月", "x": 255, "y": 65}]'
    points = _parse_grounding(text, LABELS)
    assert points == [(165.0, 95.0), (55.0, 45.0), (255.0, 65.0)]


def test_parse_json_in_code_block():
    text = "识别结果如下：\n```json\n[{\"label\": \"河\", \"x\": 10, \"y\": 20}, {\"label\": \"山\", \"x\": 30, \"y\": 40}, {\"label\": \"月\", \"x\": 50, \"y\": 60}]\n```"
    points = _parse_grounding(text, LABELS)
    assert points == [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]


def test_parse_reorders_by_label():
    # 模型乱序返回时按给定 labels 顺序取点
    text = '[{"label": "月", "x": 5, "y": 6}, {"label": "河", "x": 1, "y": 2}, {"label": "山", "x": 3, "y": 4}]'
    points = _parse_grounding(text, LABELS)
    assert points == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


def test_parse_missing_label_fails():
    text = '[{"label": "河", "x": 1, "y": 2}, {"label": "山", "x": 3, "y": 4}]'
    assert _parse_grounding(text, LABELS) is None


def test_parse_garbage_returns_none():
    assert _parse_grounding("我找不到", LABELS) is None
    assert _parse_grounding("", LABELS) is None
