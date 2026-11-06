"""poster_brief — 商品海报的表单面板。

与 ``image_brief`` 分开而不是加个「模式」开关：A2UI 面板是静态 IR（无 showIf），
且历史回放要能一眼看出「当时填的是海报表单还是自由创作表单」——这正是
``image_brief`` 注释里写过的原则（一个工具两种形态，回放无法判断）。

字段对齐线下门店做图的最小必要集：商品图 / 商品名称 / 核心卖点 / 风格 / 比例。
**文案不交给模型画**：面板收集的中文由 ``poster.layout`` 用系统字体合成。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...media import active_image_provider, image_capabilities
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..poster.prompt import STYLE_LABELS
from ..registry import register_tool
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

SURFACE_ID = "poster-params"

#: 比例选项：海报以竖版为主，方形用于朋友圈九宫格
_RATIO_OPTIONS = ("3:4", "9:16", "1:1")

_STYLE_DESCS = {
    "clean": "干净背景、柔和光，适合日常上新",
    "promo": "高饱和暖光、强冲击，适合促销",
    "premium": "深色背景、侧逆光，适合高端线",
}


def prepare(arguments: dict[str, Any]) -> dict[str, Any]:
    """确定性构建面板 IR（纯函数：无 IO、不依赖网络）。"""
    arguments = arguments or {}
    from app.config import settings_store

    settings = settings_store.load()
    provider = active_image_provider(settings)
    caps = image_capabilities(provider)
    supports_reference = bool(caps["supports_reference"])

    form = {
        "product_image": "",
        "product_name": "",
        "selling_points": "",
        "style": "clean",
        "aspect_ratio": "3:4",
    }

    children: list[str] = []
    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "gap": "md", "children": children}
    ]

    def _add(component: dict[str, Any], attach: bool = True) -> None:
        components.append(component)
        if attach:
            children.append(component["id"])

    _add(
        {
            "id": "intro",
            "component": "Text",
            "text": "海报由「商品底图 + 系统排版文字」两步合成：画面交给模型，文案用字体绘制——中文不会出现错字。",
            "variant": "caption",
        }
    )

    if not supports_reference:
        _add(
            {
                "id": "provider_warn",
                "component": "Text",
                "text": "当前生效的图像模型不支持参考图，海报无法保留商品原样。请到「设置 → 生成模型」启用 MiniMax（image-01）后再试。",
                "variant": "caption",
            }
        )

    # —— 商品图（必填）——
    _add(
        {
            "id": "product_label",
            "component": "Text",
            "text": "商品图（必填）",
            "variant": "h4",
        }
    )
    _add(
        {
            "id": "product_pick",
            "component": "FilePicker",
            "label": "",
            "value": {"path": "/form/product_image"},
            "accept": "image",
            "placeholder": "选一张商品照片（JPG / PNG / WebP）",
        }
    )
    _add(
        {
            "id": "product_note",
            "component": "Text",
            "text": "建议主体清晰、背景干净的实拍图；白底图效果最好。",
            "variant": "caption",
        }
    )

    # —— 商品名称（必填）——
    _add(
        {
            "id": "name_field",
            "component": "TextField",
            "label": "商品名称（必填）",
            "value": {"path": "/form/product_name"},
            "required": True,
            "placeholder": "如：招牌杨枝甘露",
        }
    )
    _add(
        {
            "id": "name_note",
            "component": "Text",
            "text": "会作为海报主标题，建议 12 字以内。",
            "variant": "caption",
        }
    )

    # —— 核心卖点 ——
    _add(
        {
            "id": "points_field",
            "component": "TextArea",
            "label": "核心卖点（每行一条，最多 4 条）",
            "value": {"path": "/form/selling_points"},
            "rows": 4,
        }
    )
    _add(
        {
            "id": "points_note",
            "component": "Text",
            "text": "如：现做现卖，只用当日鲜果 / 甜度可调 / 第二杯半价。卖点既会画进构图，也会以文字排在海报底部。",
            "variant": "caption",
        }
    )

    # —— 风格 ——
    _add(
        {"id": "style_label", "component": "Text", "text": "海报风格", "variant": "h4"}
    )
    _add(
        {
            "id": "style_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/style"},
            "options": [
                {"value": key, "label": STYLE_LABELS[key], "desc": _STYLE_DESCS[key]}
                for key in ("clean", "promo", "premium")
            ],
        }
    )

    # —— 比例 ——
    _add(
        {"id": "ratio_label", "component": "Text", "text": "画面比例", "variant": "h4"}
    )
    _add(
        {
            "id": "ratio_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/aspect_ratio"},
            "columns": 3,
            "options": [
                {"value": ratio, "label": ratio, "icon": f"ratio-{ratio.replace(':', '-')}"}
                for ratio in _RATIO_OPTIONS
            ],
        }
    )

    # —— 动作行 ——
    context = [
        {"key": "product_image", "value": {"path": "/form/product_image"}},
        {"key": "product_name", "value": {"path": "/form/product_name"}},
        {"key": "selling_points", "value": {"path": "/form/selling_points"}},
        {"key": "style", "value": {"path": "/form/style"}},
        {"key": "aspect_ratio", "value": {"path": "/form/aspect_ratio"}},
    ]
    _add({"id": "ops", "component": "Row", "gap": "sm", "children": ["go", "cancel"]})
    _add(
        {
            "id": "go",
            "component": "Button",
            "variant": "primary",
            "text": "生成海报",
            "action": {"name": "poster_create", "context": context},
        },
        attach=False,
    )
    _add(
        {
            "id": "cancel",
            "component": "Button",
            "variant": "ghost",
            "text": "取消",
            "action": {"name": "cancel"},
        },
        attach=False,
    )

    surface_id = str(arguments.get("surface_id") or SURFACE_ID)
    surface = {
        "surfaceId": surface_id,
        "title": "商品海报",
        "actions": ["poster_create"],
        "components": components,
        "data": {
            "form": form,
            "provider": provider,
            "capabilities": {
                "supports_reference": supports_reference,
                "ratios": list(_RATIO_OPTIONS),
            },
        },
    }
    return {"surface": surface, "surface_id": surface_id, "provider": provider}


@register_tool(
    "poster_brief",
    "做「商品海报」前先弹表单：商品图（必填）/ 商品名称（必填）/ 核心卖点 / 风格 / 比例。"
    "**何时调用**：用户要做商品海报、促销图、上新图、门店宣传图时先调本工具；"
    "只是想要插画、壁纸、配图（没有具体商品与文案）时用 image_brief。"
    "收到 poster_create 回流后按参数调用 poster_generate，不要二次确认。",
    {
        "type": "object",
        "properties": {
            "surface_id": {
                "type": "string",
                "description": "可选；面板 id，刷新时保持不变即可原地更新",
            },
        },
    },
)
class PosterBriefAdapter(ToolAdapter):
    """只出表单、不生成。"""

    category = "ui"
    timeout = 10

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del workspace, locale, progress_callback

        prepared = prepare(arguments or {})
        surface = prepared["surface"]
        validation = validate_ui_surface(surface)
        if not validation.ok:
            first = validation.errors[0] if validation.errors else None
            raise ToolExecutionError(
                f"海报表单构建失败（{first.path}）：{first.message}"
                if first
                else "海报表单构建失败：校验未通过"
            )

        normalized = validation.normalized or surface
        messages = to_messages(normalized)

        note = (
            "✓ 已弹出商品海报表单（商品图 / 商品名称 / 核心卖点 / 风格 / 比例）。"
            "用户点「生成海报」后，按回流参数调用 poster_generate，"
            "参数以表单值为准，不要二次确认，也不要自行改写。"
            "面板自带「生成海报/取消」按钮，正文中禁止再输出按钮或 ```options 动作块。"
        )

        return ToolResult(
            success=True,
            message=note,
            content=json.dumps(
                {
                    "success": True,
                    "message": note,
                    "surfaceId": prepared["surface_id"],
                    "provider": prepared["provider"],
                },
                ensure_ascii=False,
            ),
            data={
                "uiSurface": normalized,
                "a2uiMessages": messages,
                "surfaceId": prepared["surface_id"],
                "actionNames": ["poster_create"],
            },
        )


def surface_from_args(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """落库回放用：入参 → 面板 IR。"""
    try:
        return prepare(arguments or {})["surface"]
    except Exception:  # noqa: BLE001 - 落库不得因面板异常而失败
        return None
