"""中立 IR 的提取与重建。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §5.3。

为什么要有这个模块：模型给 ``render_ui`` 的参数有**两种形态**（顶层扁平字段，
或 ``surface`` 嵌套别名），而 IR 有两个消费方 —— 适配器（渲染当下）与持久化
（回合结束回放）。两处若各写一份提取逻辑，"渲染出来的面板"和"回放出来的面板"
迟早会分叉。所以提取逻辑只在这里存在一份。
"""

from __future__ import annotations

from typing import Any

from .catalog import SURFACE_TOP_KEYS


def extract_surface(arguments: dict[str, Any]) -> dict[str, Any]:
    """把工具参数折成一个中立 IR 对象。

    优先级：顶层字段覆盖 ``surface`` 嵌套里的同名字段（顶层更具体）。
    只认 ``SURFACE_TOP_KEYS`` 里的键，其余（含模型幻觉出的字段）一律丢弃 ——
    未知字段由 ``validator`` 在原始参数上单独报错，不在这里静默吞掉。
    """
    source: dict[str, Any] = {}
    nested = arguments.get("surface")
    if isinstance(nested, dict):
        for key in SURFACE_TOP_KEYS:
            if key in nested:
                source[key] = nested[key]
    for key in SURFACE_TOP_KEYS:
        if key in arguments:
            source[key] = arguments[key]
    return source
