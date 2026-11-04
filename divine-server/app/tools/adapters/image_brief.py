"""image_brief — 图像生成的参数确认面板（036）。

与 ``flight_board`` / ``video_brief`` 同一模式：**模型不产出 A2UI JSON**，
本工具按「当前生效图像模型的能力」确定性拼出中立 IR，服务端校验后渲染。
选项里**不会出现该模型不支持的项目**（GLM 没有参考图那一行、数量只有 1 张、
比例里没有 21:9 —— "不渲染"优于"点了才发现被改"）。

为什么独立成工具而不是让 ``image_generate`` 顺手出面板：
一个工具有时出图、有时出表单，回放历史时无法判断"当时是哪种"。

面板不承载 prompt（来自对话原文），只收：参考图 / 数量 / 画面比例 / 提示词优化。
用户点「开始生成」→ 动作 ``image_create`` 回流 → 模型**按回流参数**调用
``image_generate``，不要再弹一次卡。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...media import active_image_provider, image_capabilities, image_defaults
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

SURFACE_ID = "image-params"

#: 数量选项文案
_N_LABELS = {1: "1 张", 2: "2 张", 3: "3 张", 4: "4 张"}


def prepare(arguments: dict[str, Any]) -> dict[str, Any]:
    """确定性构建面板 IR（纯函数：无 IO、不依赖网络）。

    实时渲染（``run``）与回合收尾的落库回放共用这一份。
    """
    arguments = arguments or {}
    from app.config import settings_store

    settings = settings_store.load()
    provider = active_image_provider(settings)
    caps = image_capabilities(provider)
    defaults = image_defaults(settings, provider)

    form = {
        "reference_image": "",
        "n": defaults["n"],
        "aspect_ratio": defaults["aspect_ratio"],
        "prompt_optimizer": defaults["prompt_optimizer"],
    }

    children: list[str] = []
    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "gap": "md", "children": children}
    ]

    def _add(component: dict[str, Any], attach: bool = True) -> None:
        """注册组件；attach=False 表示只被其它容器（如动作 Row）引用，不挂根 children。

        挂根会让被引用的子组件**再渲染一遍**（用户看到两组「开始生成/取消」，2026-11-04）。
        """
        components.append(component)
        if attach:
            children.append(component["id"])

    # —— 参考图（仅支持的 provider 渲染；不渲染优于点了才发现不支持）——
    if caps["supports_reference"]:
        _add(
            {
                "id": "ref_label",
                "component": "Text",
                "text": "参考图（选填）",
                "variant": "h4",
            }
        )
        _add(
            {
                "id": "ref_pick",
                "component": "FilePicker",
                "label": "",
                "value": {"path": "/form/reference_image"},
                "accept": "image",
                "placeholder": "不选为文生图；选了按这张图生成",
            }
        )
        _add(
            {
                "id": "ref_note",
                "component": "Text",
                "text": "参考图以最终选定的文件为准；生成时请勿再改写。",
                "variant": "caption",
            }
        )

    # —— 数量（GLM 固定 1 张，不渲染选择器）——
    n_max = int(caps["n_max"])
    if n_max > 1:
        _add(
            {
                "id": "n_label",
                "component": "Text",
                "text": "生成数量",
                "variant": "h4",
            }
        )
        _add(
            {
                "id": "n_pick",
                "component": "ChoicePicker",
                "value": {"path": "/form/n"},
                "options": [
                    {"value": str(n), "label": _N_LABELS.get(n, f"{n} 张")}
                    for n in range(1, n_max + 1)
                ],
            }
        )

    # —— 画面比例（3 列网格 + CSS 比例图标；GLM 不给 21:9）——
    _add(
        {
            "id": "ratio_label",
            "component": "Text",
            "text": "画面比例",
            "variant": "h4",
        }
    )
    ratio_options = [{"value": "", "label": "智能", "icon": "ratio-auto"}] + [
        {"value": ratio, "label": ratio, "icon": f"ratio-{ratio.replace(':', '-')}"}
        for ratio in caps["ratios"]
    ]
    _add(
        {
            "id": "ratio_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/aspect_ratio"},
            "columns": 3,
            "options": ratio_options,
        }
    )

    # —— 提示词优化（仅 MiniMax）——
    if caps["prompt_optimizer"]:
        _add(
            {
                "id": "opt_switch",
                "component": "Switch",
                "label": "自动优化提示词",
                "checked": {"path": "/form/prompt_optimizer"},
            }
        )

    # —— 动作行 ——
    context = [
        {"key": "reference_image", "value": {"path": "/form/reference_image"}},
        {"key": "n", "value": {"path": "/form/n"}},
        {"key": "aspect_ratio", "value": {"path": "/form/aspect_ratio"}},
    ]
    if caps["prompt_optimizer"]:
        context.append(
            {"key": "prompt_optimizer", "value": {"path": "/form/prompt_optimizer"}}
        )
    _add(
        {
            "id": "ops",
            "component": "Row",
            "gap": "sm",
            "children": ["go", "cancel"],
        }
    )
    _add(
        {
            "id": "go",
            "component": "Button",
            "variant": "primary",
            "text": "开始生成",
            "action": {"name": "image_create", "context": context},
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
        "title": "图片参数",
        "actions": ["image_create"],
        "components": components,
        "data": {
            "form": form,
            "provider": provider,
            "capabilities": {
                "supports_reference": bool(caps["supports_reference"]),
                "n_max": n_max,
                "ratios": list(caps["ratios"]),
                "prompt_optimizer": bool(caps["prompt_optimizer"]),
            },
        },
    }
    return {"surface": surface, "surface_id": surface_id, "provider": provider}


@register_tool(
    "image_brief",
    "生成图像前先弹「图片参数」面板让用户确认：参考图（选填）/ 生成数量 / 画面比例 / "
    "提示词优化。**何时调用**：用户想生成图片、但没说清比例或数量时，先调本工具"
    "（不要直接猜参数生成）；用户已明确说了比例/数量，或只是上传图片要改图时，"
    "直接调 image_generate。**不要**在面板未确认时就生成。",
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
class ImageBriefAdapter(ToolAdapter):
    """只出面板、不生成（与 flight_board / video_brief 同模式）。"""

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
                f"参数面板构建失败（{first.path}）：{first.message}"
                if first
                else "参数面板构建失败：校验未通过"
            )

        normalized = validation.normalized or surface
        messages = to_messages(normalized)

        note = (
            "✓ 已弹出图片参数面板（参考图 / 数量 / 比例）。"
            "用户点「开始生成」后，按回流参数调用 image_generate，"
            "参数以面板值为准，不要二次确认，也不要自行改写。"
            "面板自带「开始生成/取消」按钮，正文中禁止再输出按钮或 ```options 动作块。"
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
                "actionNames": ["image_create"],
            },
        )


def surface_from_args(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """落库回放用：入参 → 面板 IR（与 flight_board.surface_from_args 同约定）。"""
    try:
        return prepare(arguments or {})["surface"]
    except Exception:  # noqa: BLE001 - 落库不得因面板异常而失败
        return None
