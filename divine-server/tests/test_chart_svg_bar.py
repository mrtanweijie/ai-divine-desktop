"""SVG 图表导出（render_chart_svg）柱状图样式回归测试。

原缺陷：纵向柱状图柱宽按 group_width * 0.72 计算且无上限，
分类少时（如 3 个）柱子宽达 160px，且在组内左对齐、偏离分类标签。
"""

import re

from app.docgen.chart.svg import render_chart_svg


def _rects(svg: str) -> list[tuple[float, float, float, float]]:
    """提取柱体 rect 的 (x, y, width, height)，过滤图例色块（10×10）。"""
    return [
        (float(m[0]), float(m[1]), float(m[2]), float(m[3]))
        for m in re.findall(
            r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" '
            r'height="([\d.]+)" rx="2"',
            svg,
        )
        if (float(m[2]), float(m[3])) != (10.0, 10.0)
    ]


def _bar_option(categories: list[str], values: list[float]) -> dict:
    return {
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "name": "系列", "data": values}],
    }


def test_few_categories_bar_width_capped():
    """分类少时柱宽必须封顶（对齐前端 barMaxWidth: 30），不能撑满分组。"""
    svg = render_chart_svg(
        _bar_option(["寒武纪", "摩尔线程", "燧原科技"], [59.96, 17.36, 11.2]),
        "营收对比",
    )
    rects = _rects(svg)
    assert len(rects) == 3
    for _, _, bar_width, _ in rects:
        assert bar_width <= 30.0


def test_bars_centered_in_category_groups():
    """柱体应在其分类分组内水平居中，与分类标签对齐。"""
    categories = ["寒武纪", "摩尔线程", "燧原科技"]
    svg = render_chart_svg(
        _bar_option(categories, [59.96, 17.36, 11.2]),
        "营收对比",
    )
    rects = _rects(svg)
    left, right = 72, 24
    group_width = (760 - left - right) / len(categories)
    for index, (x, _, _, _) in enumerate(rects):
        bar_center = x + 15
        group_center = left + (index + 0.5) * group_width
        assert abs(bar_center - group_center) < 1.0


def test_multi_series_bars_grouped_and_centered():
    """多系列时各柱并排且整组居中。"""
    categories = ["A", "B"]
    svg = render_chart_svg(
        {
            "xAxis": {"type": "category", "data": categories},
            "yAxis": {"type": "value"},
            "series": [
                {"type": "bar", "name": "系列一", "data": [10, 20]},
                {"type": "bar", "name": "系列二", "data": [15, 25]},
            ],
        },
        "对比",
    )
    rects = _rects(svg)
    assert len(rects) == 4
    for _, _, bar_width, _ in rects:
        assert bar_width <= 30.0
    # 每组两根柱子并排（第二根 x = 第一根 x + 柱宽）
    group_a = sorted(x for x, _, _, _ in rects if x < 760 / 2)
    assert len(group_a) == 2
    assert group_a[1] - group_a[0] == rects[0][2]


def test_many_categories_unchanged():
    """分类多时行为不变（0.72 占比仍低于 30 上限时不受影响）。"""
    categories = [f"分类{i}" for i in range(20)]
    svg = render_chart_svg(_bar_option(categories, list(range(20))), "分布")
    rects = _rects(svg)
    assert len(rects) == 20
    expected = (760 - 72 - 24) / 20 * 0.72
    for _, _, bar_width, _ in rects:
        assert abs(bar_width - expected) < 0.5
