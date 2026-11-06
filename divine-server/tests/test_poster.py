"""商品海报（poster_brief / poster_generate / poster.layout）的守卫测试。

重点守住三件事：
1. 卖点拆分与截断的边界（换行/分号/顿号、去重、4 条上限）；
2. 排版在极端文案下**不抛异常**且输出尺寸正确（字号/条数会逐级收缩）；
3. 表单 IR 能通过 L2 校验，且动作与字段绑定齐全。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.tools.adapters.poster_brief import prepare as prepare_brief
from app.tools.adapters.poster_generate import _safe_name, _split_points
from app.tools.poster.layout import PosterText, compose
from app.tools.poster.prompt import build_prompt
from app.tools.ui.validator import validate_ui_surface


@pytest.fixture()
def base_image(tmp_path):
    path = tmp_path / "base.png"
    Image.new("RGB", (768, 768), "#3a3f47").save(path)
    return path


def test_split_points_supports_newline_semicolon_and_dunhao() -> None:
    assert _split_points("现做现卖\n甜度可调；第二杯半价、加料免费") == [
        "现做现卖",
        "甜度可调",
        "第二杯半价",
        "加料免费",
    ]


def test_split_points_keeps_chinese_comma_inside_sentence() -> None:
    """中文逗号是句内停顿，不该把一句卖点拆成两条。"""
    assert _split_points("现做现卖，2 小时送达") == ["现做现卖，2 小时送达"]


def test_split_points_dedups_and_caps_at_four() -> None:
    assert _split_points("a\nb\nc\nd\ne\na") == ["a", "b", "c", "d"]


def test_safe_name_strips_path_separators() -> None:
    assert _safe_name("招牌/杨枝*甘露 500ml") == "招牌杨枝甘露500ml"
    assert _safe_name("///") == "poster"


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [("3:4", (1080, 1440)), ("9:16", (1080, 1920)), ("1:1", (1080, 1080))],
)
def test_compose_writes_expected_canvas(base_image, tmp_path, ratio, expected) -> None:
    out = compose(
        base_image,
        PosterText(title="招牌杨枝甘露", points=["现做现卖", "甜度可调"]),
        tmp_path / "poster.png",
        aspect_ratio=ratio,
    )
    assert out.exists()
    assert Image.open(out).size == expected


def test_compose_survives_overlong_copy(base_image, tmp_path) -> None:
    """超长标题 + 4 条长卖点：只允许收缩排版，不允许报错（否则最后一步白跑）。"""
    out = compose(
        base_image,
        PosterText(
            title="超长商品名称测试一二三四五六七八九十",
            points=[
                "第一条卖点写得非常非常长需要自动收缩排版不能溢出画布",
                "第二条",
                "第三条",
                "第四条",
            ],
        ),
        tmp_path / "long.png",
        aspect_ratio="9:16",
    )
    assert out.exists()
    assert Image.open(out).size == (1080, 1920)


def test_compose_handles_empty_points(base_image, tmp_path) -> None:
    out = compose(
        base_image, PosterText(title="单人下午茶", points=[]), tmp_path / "p.png"
    )
    assert out.exists()


def test_brief_surface_passes_validation() -> None:
    surface = prepare_brief({})["surface"]
    result = validate_ui_surface(surface)
    assert result.ok, [f"{item.path}: {item.message}" for item in result.errors]

    ids = {component["id"] for component in surface["components"]}
    assert {"product_pick", "name_field", "points_field", "style_pick", "ratio_pick"} <= ids
    assert surface["actions"] == ["poster_create"]

    go = next(item for item in surface["components"] if item["id"] == "go")
    keys = [entry["key"] for entry in go["action"]["context"]]
    assert keys == [
        "product_image",
        "product_name",
        "selling_points",
        "style",
        "aspect_ratio",
    ]
    # 动作按钮只被 ops Row 引用，不能同时挂根（否则渲染两组按钮）
    root = next(item for item in surface["components"] if item["id"] == "root")
    assert "go" not in root["children"]
    ops = next(item for item in surface["components"] if item["id"] == "ops")
    assert ops["children"] == ["go", "cancel"]


def test_build_prompt_forbids_text_and_keeps_blank_area() -> None:
    prompt = build_prompt(
        product_name="招牌杨枝甘露",
        selling_points=["现做现卖"],
        style="clean",
        aspect_ratio="3:4",
    )
    assert "招牌杨枝甘露" in prompt
    assert "不要出现任何文字" in prompt
    assert "底部" in prompt


def _png(path, size=(640, 640), color="#404650"):
    Image.new("RGB", size, color).save(path)
    return path


def test_poster_generate_stitches_base_and_text(monkeypatch, tmp_path):
    """编排逻辑：调 image_generate 出底图 → 叠字 → 删底图 → 返回海报。

    用假 adapter 顶替 image_generate（不联网、不花钱），只验证海报这一层。
    """
    import asyncio

    from app.tools.adapters import poster_generate as module
    from app.tools.base import ToolResult
    from app.tools.registry import registry

    product = _png(tmp_path / "product.png")
    base = _png(tmp_path / "base.png", (1024, 1024))
    calls: dict[str, object] = {}

    class FakeImageAdapter:
        async def run(self, workspace, arguments, locale=None, progress_callback=None):
            calls.update(arguments)
            return ToolResult(
                success=True,
                message="ok",
                file_name="base.png",
                filepath=str(base),
                data={"provider": "minimax", "model": "image-01"},
            )

    monkeypatch.setitem(registry._tools, "image_generate", FakeImageAdapter())
    monkeypatch.setattr(module, "active_image_provider", lambda settings: "minimax")
    monkeypatch.setattr(
        module, "image_capabilities", lambda provider: {"supports_reference": True}
    )
    monkeypatch.setattr(
        module, "output_dir_for_workspace", lambda workspace: tmp_path / "output"
    )

    adapter = module.PosterGenerateAdapter("poster_generate", "d", {})
    result = asyncio.run(
        adapter.run(
            tmp_path,
            {
                "product_image": str(product),
                "product_name": "招牌杨枝甘露",
                "selling_points": "现做现卖\n甜度可调",
                "style": "clean",
                "aspect_ratio": "3:4",
            },
        )
    )

    out = Path(result.filepath)
    assert out.exists()
    assert out.parent == tmp_path / "output" / "posters"
    assert Image.open(out).size == (1080, 1440)
    # 底图是中间产物，成功后必须清掉（否则卡片墙多一张无字图）
    assert not base.exists()
    # 传给底图模型的提示词必须带「不要文字」与商品图
    assert calls["reference_image"] == str(product.resolve())
    assert "不要出现任何文字" in str(calls["prompt"])
    # 卡片墙靠 data.files 取路径
    assert result.data["files"][0]["path"] == str(out)
    assert result.data["provider"] == "minimax"
