"""参数面板布局守卫（2026-11-04）。

**为什么要有这条测试**：`video_brief` / `image_brief` 用局部函数 `_add()` 同时
「注册组件」和「挂到根 children」。动作按钮 go/cancel 只应被 `ops` Row 引用，
若也挂到根 children，前端会**再渲染一遍**——用户看到两组「开始生成/取消」
（2026-11-04 实锤）。这里直接断言面板结构，防止 `_add` 语义回退。
"""

from __future__ import annotations

import pytest

from app.tools.adapters import image_brief, video_brief


def _root_children(surface: dict) -> list[str]:
    components = surface["components"]
    root = next(item for item in components if item["id"] == surface.get("rootId", "root"))
    return list(root.get("children") or [])


def _by_id(surface: dict, component_id: str) -> dict:
    return next(item for item in surface["components"] if item["id"] == component_id)


@pytest.mark.parametrize(
    ("module", "action_name"),
    [(video_brief, "video_create"), (image_brief, "image_create")],
)
def test_action_buttons_hang_only_on_ops_row(module, action_name: str) -> None:
    surface = module.prepare({})["surface"]
    children = _root_children(surface)

    # 动作按钮**不许**出现在根 children 里（否则会被渲染第二次）
    assert "go" not in children
    assert "cancel" not in children
    # 但它们必须被 ops Row 引用，否则按钮彻底消失
    ops = _by_id(surface, "ops")
    assert ops["children"] == ["go", "cancel"]
    # ops 本身要挂在根上（否则整行动作不可见）
    assert "ops" in children

    # 动作名对齐（防止 detach 时误改动作绑定）
    assert _by_id(surface, "go")["action"]["name"] == action_name
    assert _by_id(surface, "cancel")["action"]["name"] == "cancel"


@pytest.mark.parametrize("module", [video_brief, image_brief])
def test_file_picker_label_left_empty(module) -> None:
    """FilePicker 外层已有 Text h4 标题：label 必须留空，否则出现双标题。

    2026-11-04 用户反馈两次（video 首帧/尾帧、image 参考图）——前端已支持空串
    不渲染 label 行，这里守住 adapter 侧不再写死文案。
    """
    surface = module.prepare({})["surface"]
    pickers = [item for item in surface["components"] if item["component"] == "FilePicker"]
    assert pickers, "面板应至少有一个 FilePicker"
    for picker in pickers:
        assert picker["label"] == ""
