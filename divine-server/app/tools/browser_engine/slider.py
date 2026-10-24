"""滑块验证码自动求解（032 §3 L2.5，实验性）。

三层：
1. 缺口识别：Pillow 像素分析——双图差分（背景图 + 缺口拼图，最可靠）或
   单图列差分扫描（找缺口描边/阴影的显著边缘峰）；
2. 拟人轨迹：分段缓动 + 过冲回拉 + y 轴微抖 + 随机时步——不用 Playwright
   自带 drag_to（直线匀速必被行为风控识别）；
3. 重试护栏：引擎层 ≤2 次，失败降级人工（032 §3 L4）。

诚实预期：缺口识别稳定，但行为风控（时序/加速度熵）下轨迹通过率 30-70%，
且失败会累积风险分——本模块定位为「自动尝试 ≤2 次」的实验性能力，不是承诺能力。
"""

from __future__ import annotations

import io
import random


def detect_gap_x(
    bg_bytes: bytes,
    piece_bytes: bytes | None = None,
    search_from: int = 0,
) -> int | None:
    """返回缺口左缘在截图中的 x 像素；识别不出返回 None。

    - piece_bytes 提供时：背景图与缺口拼图逐列 SAD 模板匹配（最可靠）；
    - 仅背景图时：按列灰度差分找最显著边缘峰（缺口描边/阴影）；
    - search_from：探测起点像素（跳过滑块手柄自身，避免起点边缘误匹配）。
    """
    try:
        from PIL import Image
    except ImportError:  # noqa: BLE001 — Pillow 缺失直接放弃，调用方降级人工
        return None

    bg = Image.open(io.BytesIO(bg_bytes)).convert("L")
    w, h = bg.size
    if w < 40 or h < 20:
        return None
    start = max(1, min(int(search_from), w - 20))

    if piece_bytes:
        piece = Image.open(io.BytesIO(piece_bytes)).convert("L")
        pw, ph = piece.size
        if pw < 8 or ph < 8 or pw >= w or ph > h:
            return None
        px_bg = bg.load()
        px_pc = piece.load()
        sample_x = max(1, pw // 10)
        sample_y = max(1, ph // 8)
        best_x: int | None = None
        best_score: float | None = None
        for x in range(start, w - pw, 2):
            sad = 0
            count = 0
            for dx in range(0, pw, sample_x):
                for dy in range(0, ph, sample_y):
                    sad += abs(px_bg[x + dx, dy] - px_pc[dx, dy])
                    count += 1
            score = sad / max(1, count)
            if best_score is None or score < best_score:
                best_score = score
                best_x = x
        return best_x

    # 单图：按列灰度差分找最显著边缘（缺口描边/阴影）
    px = bg.load()
    step = max(1, h // 60)
    diffs: list[int] = []
    for x in range(1, w):
        d = sum(abs(px[x, y] - px[x - 1, y]) for y in range(0, h, step))
        diffs.append(d)
    search = diffs[start:]
    if not search or max(search) <= 0:
        return None
    return start + search.index(max(search))


def human_track(
    distance: float, rng: random.Random | None = None
) -> list[tuple[float, float, int]]:
    """生成拟人拖拽轨迹：[(累计x偏移, y抖动, 间隔ms), ...]。

    分段速度：慢启动 → 加速 → 匀速 → 减速 → 过冲 → 回拉精确停靠；
    y 轴随机游走限幅 ±2px；总时长 550-900ms、26-40 步、步间隔抖动。
    """
    rng = rng or random.Random()
    if distance <= 0:
        return [(distance, 0.0, 120)]

    overshoot = rng.uniform(2.0, 6.0) if distance > 40 else rng.uniform(0.5, 2.0)
    steps = rng.randint(26, 40)
    total_ms = rng.uniform(550.0, 900.0)

    weights: list[float] = []
    for i in range(steps):
        t = (i + 1) / steps
        if t < 0.15:
            w = 0.3 + 1.4 * (t / 0.15)
        elif t < 0.55:
            w = 1.7 + 0.3 * ((t - 0.15) / 0.4)
        elif t < 0.8:
            w = 2.0 - 1.2 * ((t - 0.55) / 0.25)
        else:
            w = 0.8 - 0.7 * ((t - 0.8) / 0.2)
        weights.append(max(w, 0.12))
    total_w = sum(weights)

    fracs = [0.0]
    acc = 0.0
    for wgt in weights:
        acc += wgt / total_w
        fracs.append(acc)

    moves: list[tuple[float, float, int]] = []
    y = 0.0
    target_with_over = distance + overshoot
    for frac in fracs[1:]:
        y = max(-2.0, min(2.0, y + rng.uniform(-0.8, 0.8)))
        delay = max(6, int(total_ms / steps * rng.uniform(0.6, 1.5)) + 1)
        moves.append((round(frac * target_with_over, 2), round(y, 2), delay))

    # 过冲回拉：1-2 步从过冲点收敛到精确 distance
    cur = moves[-1][0]
    back_steps = rng.randint(1, 2)
    for i in range(back_steps, 0, -1):
        target = distance + (cur - distance) * (i - 1) / back_steps
        moves.append(
            (round(target, 2), round(rng.uniform(-0.5, 0.5), 2), rng.randint(20, 60))
        )
    moves.append((round(distance, 2), 0.0, rng.randint(60, 120)))
    return moves
