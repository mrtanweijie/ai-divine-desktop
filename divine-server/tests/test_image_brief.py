"""图像参数面板（image_brief，036）的回归测试。

三个着眼点：
1. 能力差异体现在**渲染**上——不支持的项目根本不出现在 IR 里；
2. 默认值链路：media_models options > image_defaults > 出厂默认；
3. 面板 IR 必须过 L2 校验并生成 A2UI 消息（挂到 uiSurface 的前提）。
"""

from __future__ import annotations

from app.tools.adapters.image_brief import prepare, surface_from_args
from app.tools.ui.validator import validate_ui_surface
from app.tools.ui.versions.v0_9_1 import to_messages


def _component(surface: dict, component_id: str) -> dict | None:
    return next(
        (item for item in surface["components"] if item["id"] == component_id), None
    )


def _with_settings(monkeypatch, settings: dict) -> None:
    from app.config import settings_store

    monkeypatch.setattr(settings_store, "load", lambda: settings)


def test_minimax_panel_has_all_sections(monkeypatch) -> None:
    _with_settings(monkeypatch, {})
    prepared = prepare({})
    surface = prepared["surface"]
    assert prepared["provider"] == "minimax"

    ids = {item["id"] for item in surface["components"]}
    # MiniMax 全能力：参考图 / 数量 / 比例 / 提示词优化都在
    assert {"ref_pick", "n_pick", "ratio_pick", "opt_switch"} <= ids
    assert surface["actions"] == ["image_create"]


def test_glm_panel_hides_unsupported(monkeypatch) -> None:
    """GLM：无图生图、数量固定 1、比例没有 21:9 —— 不渲染，而不是渲染了再报错。"""
    _with_settings(
        monkeypatch,
        {
            "media_models": [
                {
                    "id": "m1",
                    "kind": "image",
                    "provider": "glm",
                    "api_key": "sk-glm",
                    "active": True,
                }
            ]
        },
    )
    prepared = prepare({})
    assert prepared["provider"] == "glm"
    surface = prepared["surface"]
    ids = {item["id"] for item in surface["components"]}
    assert "ref_pick" not in ids, "GLM 不支持图生图，参考图行不该出现"
    assert "n_pick" not in ids, "GLM 数量固定 1，选择器不该出现"
    assert "opt_switch" not in ids, "GLM 无提示词优化，开关不该出现"

    ratio = _component(surface, "ratio_pick")
    assert ratio is not None
    values = [option["value"] for option in ratio["options"]]
    assert "21:9" not in values, "21:9 会被 GLM 静默降级，面板不给这一项"
    assert "" in values, "「智能」始终存在"


def test_ratio_picker_uses_grid_and_css_icons(monkeypatch) -> None:
    _with_settings(monkeypatch, {})
    ratio = _component(prepare({})["surface"], "ratio_pick")
    assert ratio["columns"] == 3
    # icon 是封闭枚举，前端画 CSS 矩形；「智能」用 ratio-auto
    assert ratio["options"][0] == {"value": "", "label": "智能", "icon": "ratio-auto"}
    assert all(option.get("icon") for option in ratio["options"])


def test_defaults_from_media_options_then_fallback(monkeypatch) -> None:
    """默认值链路：media_models.options > image_defaults > 出厂默认。"""
    _with_settings(
        monkeypatch,
        {
            "media_models": [
                {
                    "id": "m1",
                    "kind": "image",
                    "provider": "minimax",
                    "api_key": "sk",
                    "active": True,
                    "options": {"n": 4, "aspect_ratio": "16:9"},
                }
            ]
        },
    )
    form = prepare({})["surface"]["data"]["form"]
    assert form["n"] == "4"
    assert form["aspect_ratio"] == "16:9"

    # 退回 image_defaults
    _with_settings(
        monkeypatch,
        {"image_defaults": {"n": 2, "aspect_ratio": "9:16"}},
    )
    form = prepare({})["surface"]["data"]["form"]
    assert form["n"] == "2"
    assert form["aspect_ratio"] == "9:16"

    # 出厂默认：智能比例
    _with_settings(monkeypatch, {})
    form = prepare({})["surface"]["data"]["form"]
    assert form["n"] == "1"
    assert form["aspect_ratio"] == ""


def test_invalid_saved_ratio_falls_back_to_auto(monkeypatch) -> None:
    """历史遗留的 21:9（比如从 MiniMax 切到 GLM）不能把非法值带给 provider。"""
    _with_settings(
        monkeypatch,
        {
            "media_models": [
                {
                    "id": "m1",
                    "kind": "image",
                    "provider": "glm",
                    "api_key": "sk",
                    "active": True,
                    "options": {"aspect_ratio": "21:9"},
                }
            ]
        },
    )
    form = prepare({})["surface"]["data"]["form"]
    assert form["aspect_ratio"] == ""


def test_panel_passes_l2_and_emits_messages(monkeypatch) -> None:
    """挂到 uiSurface 的前提：L2 校验通过 + 能翻成 A2UI 消息。"""
    _with_settings(monkeypatch, {})
    surface = prepare({})["surface"]
    validation = validate_ui_surface(surface)
    assert validation.ok, [e.message for e in validation.errors]
    messages = to_messages(validation.normalized or surface)
    assert len(messages) >= 1


def test_unknown_option_icon_rejected(monkeypatch) -> None:
    """icon 是封闭枚举：写 lucide 名字 / 图片地址直接被 L2 拦下。"""
    _with_settings(monkeypatch, {})
    surface = prepare({})["surface"]
    ratio = _component(surface, "ratio_pick")
    assert ratio is not None
    ratio["options"][0]["icon"] = "camera"  # 模拟模型发明图标名
    validation = validate_ui_surface(surface)
    assert not validation.ok
    assert any("icon" in error.path for error in validation.errors)


def test_surface_from_args_rebuilds_for_persistence(monkeypatch) -> None:
    """回合收尾落库回放：入参几乎为空也能重建同一块面板。"""
    _with_settings(monkeypatch, {})
    rebuilt = surface_from_args({"surface_id": "image-params"})
    assert rebuilt is not None
    assert rebuilt["surfaceId"] == "image-params"
    assert validate_ui_surface(rebuilt).ok


def test_action_context_covers_all_form_fields(monkeypatch) -> None:
    """回流 context 必须覆盖面板收集的每个字段——漏一个就是静默丢参数。"""
    _with_settings(monkeypatch, {})
    surface = prepare({})["surface"]
    go = _component(surface, "go")
    assert go is not None
    keys = {item["key"] for item in go["action"]["context"]}
    form = surface["data"]["form"]
    if "ref_pick" in {item["id"] for item in surface["components"]}:
        assert "reference_image" in keys
    if "opt_switch" in {item["id"] for item in surface["components"]}:
        assert "prompt_optimizer" in keys
    assert {"n", "aspect_ratio"} <= keys
    # context 引用的 path 必须都在 data.form 里
    for item in go["action"]["context"]:
        pointer = item["value"]["path"]
        assert pointer.startswith("/form/")
        assert pointer.split("/")[-1] in form
