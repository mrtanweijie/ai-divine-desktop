"""slider.py 纯逻辑单测：缺口检测与拟人轨迹（离线，无需浏览器）。"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw

from app.tools.browser_engine.slider import detect_gap_x, human_track

TRACK_W, TRACK_H, GAP_X, HANDLE_W = 300, 40, 180, 40


def _make_track_image(gap_x: int = GAP_X) -> bytes:
    """生成滑轨截图：浅灰背景 + 深灰缺口块（左缘 gap_x）。"""
    img = Image.new("RGB", (TRACK_W, TRACK_H), (232, 232, 232))
    draw = ImageDraw.Draw(img)
    draw.rectangle([gap_x, 0, gap_x + HANDLE_W, TRACK_H], fill=(154, 154, 154))
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_piece_image() -> bytes:
    """缺口拼图：与缺口块同色的 40x40 小图。"""
    img = Image.new("RGB", (HANDLE_W, TRACK_H), (154, 154, 154))
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# detect_gap_x
# ---------------------------------------------------------------------------


def test_detect_gap_single_image():
    # search_from 跳过手柄区（0-40）
    gap = detect_gap_x(_make_track_image(), search_from=HANDLE_W + 2)
    assert gap is not None
    assert abs(gap - GAP_X) <= 4


def test_detect_gap_two_image_diff():
    # 双图差分：背景含缺口块 + 拼图=缺口内容 → SAD 匹配
    gap = detect_gap_x(_make_track_image(), _make_piece_image(), search_from=HANDLE_W + 2)
    assert gap is not None
    assert abs(gap - GAP_X) <= 4


def test_detect_gap_none_on_tiny_image():
    import io

    tiny = Image.new("L", (10, 8))
    buf = io.BytesIO()
    tiny.save(buf, format="PNG")
    assert detect_gap_x(buf.getvalue()) is None


# ---------------------------------------------------------------------------
# human_track — 拟人轨迹性质
# ---------------------------------------------------------------------------


def _extract_moves():
    return human_track(180.0, random.Random(42))


def test_track_ends_at_exact_distance():
    moves = _extract_moves()
    assert moves[-1][0] == 180.0


def test_track_has_overshoot_before_settle():
    moves = _extract_moves()
    body = moves[:-1]  # 过冲回拉之外的主体
    assert max(m[0] for m in body) > 180.0


def test_track_step_count_bounded():
    moves = _extract_moves()
    assert 25 <= len(moves) <= 46


def test_track_monotonic_progress():
    moves = _extract_moves()
    xs = [m[0] for m in moves]
    # 主体近似递增（允许 ±2px 抖动），回拉段从峰值收敛
    rises = sum(1 for a, b in zip(xs, xs[1:]) if b >= a - 2.5)
    assert rises >= len(xs) - 3


def test_track_delays_positive():
    moves = _extract_moves()
    assert all(delay >= 6 for _, _, delay in moves)


def test_track_y_jitter_bounded():
    moves = _extract_moves()
    assert all(-2.5 <= dy <= 2.5 for _, dy, _ in moves)


def test_track_zero_distance_short_circuit():
    moves = human_track(0.0, random.Random(1))
    assert len(moves) == 1 and moves[0][0] == 0.0


def test_track_is_nondeterministic():
    a = [(round(m[0], 1), round(m[2], 0)) for m in human_track(180.0, random.Random(1))]
    b = [(round(m[0], 1), round(m[2], 0)) for m in human_track(180.0, random.Random(2))]
    assert a != b  # 两次轨迹不同（反指纹的基本要求）
