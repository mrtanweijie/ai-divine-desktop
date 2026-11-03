"""video_brief — 视频生成的参数确认面板（035 §7）。

与 ``image_brief`` / ``flight_board`` 同模式：**模型不产出 A2UI JSON**，
面板由服务端按当前生效视频模型的能力确定性拼出——不支持的项目**不渲染**
（智谱没有尾帧行；分辨率档按 provider 裁剪；单价未配置则时长档不带价格）。

面板收集：素材来源 / 资讯 URL / 首尾帧 / 比例 / 分辨率 / 时长 / 字幕 / 口播。
用户点「开始生成」→ 动作 ``video_create`` 回流 → 模型**按回流参数**调
``video_generate``（资讯模式先 web_fetch），不二次确认。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...media import service
from ...media.config import active_video_provider, video_capabilities
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

SURFACE_ID = "video-params"


def prepare(arguments: dict[str, Any]) -> dict[str, Any]:
    """确定性构建面板 IR（纯函数；实时渲染与落库回放共用）。"""
    arguments = arguments or {}
    from app.config import settings_store

    settings = settings_store.load()
    provider = active_video_provider(settings)
    caps = video_capabilities(provider)

    entry = _active_entry(settings)
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    price = _price_per_second(options)
    form = {
        "source": "custom",
        "source_url": "",
        "first_frame": "",
        "last_frame": "",
        "aspect_ratio": _default_ratio(options, caps),
        "resolution": _default_resolution(options, caps),
        "duration": str(_default_duration(options, caps)),
        "subtitles": False,
        "script": "",
    }

    children: list[str] = []
    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "gap": "md", "children": children}
    ]

    def _add(component: dict[str, Any]) -> None:
        components.append(component)
        children.append(component["id"])

    # —— 素材来源（§7.9：资讯视频。A2UI 无 tab/条件渲染 → 两字段常驻 + 校验兜底）——
    _add(
        {
            "id": "source_label",
            "component": "Text",
            "text": "素材来源",
            "variant": "h4",
        }
    )
    _add(
        {
            "id": "source_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/source"},
            "options": [
                {"value": "custom", "label": "自定义", "desc": "直接用下面的描述生成"},
                {"value": "article", "label": "网络抓取", "desc": "抓取单篇文章后提炼要点"},
            ],
        }
    )
    _add(
        {
            "id": "source_url_field",
            "component": "TextField",
            "label": "资讯页面 URL",
            "value": {"path": "/form/source_url"},
            "placeholder": "单篇文章完整 URL（公众号文章、新闻页等）",
        }
    )
    _add(
        {
            "id": "source_note",
            "component": "Text",
            "text": "仅支持单篇文章；首页、栏目列表、搜索结果页不支持。选「网络抓取」时必填。",
            "variant": "caption",
        }
    )

    # —— 首帧 / 尾帧（能力差异 → 不渲染不支持项，§7.8）——
    _add(
        {
            "id": "frame_label",
            "component": "Text",
            "text": "首帧图（选填）",
            "variant": "h4",
        }
    )
    _add(
        {
            "id": "first_pick",
            "component": "FilePicker",
            "label": "首帧图",
            "value": {"path": "/form/first_frame"},
            "accept": "image",
            "placeholder": "不选为纯文本生成",
        }
    )
    if caps["supports_last_frame"]:
        _add(
            {
                "id": "last_label",
                "component": "Text",
                "text": "尾帧图（选填）",
                "variant": "h4",
            }
        )
        _add(
            {
                "id": "last_pick",
                "component": "FilePicker",
                "label": "尾帧图",
                "value": {"path": "/form/last_frame"},
                "accept": "image",
                "placeholder": "两张都填 = 首尾帧",
            }
        )
    _add(
        {
            "id": "frame_note",
            "component": "Text",
            "text": "留空=纯文本；只填首帧=图生视频；两张都填=首尾帧。",
            "variant": "caption",
        }
    )

    # —— 画面比例（3 列 + CSS 比例图标）——
    _add(
        {
            "id": "ratio_label",
            "component": "Text",
            "text": "画面比例",
            "variant": "h4",
        }
    )
    _add(
        {
            "id": "ratio_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/aspect_ratio"},
            "columns": 3,
            "options": [{"value": "", "label": "智能", "icon": "ratio-auto"}]
            + [
                {"value": ratio, "label": ratio, "icon": f"ratio-{ratio.replace(':', '-')}"}
                for ratio in caps["ratios"]
            ],
        }
    )

    # —— 分辨率 ——
    _add(
        {
            "id": "res_label",
            "component": "Text",
            "text": "分辨率",
            "variant": "h4",
        }
    )
    _add(
        {
            "id": "res_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/resolution"},
            "columns": 3,
            "options": [
                {"value": item, "label": item} for item in caps["resolutions"]
            ],
        }
    )

    # —— 时长（档位 desc 带预估费用，§7.10；「智能」= 交给 provider 默认）——
    # 只给 3 档常用值（12 档胶囊没法选），越界值由 video_generate 静默裁剪兜底
    _add(
        {
            "id": "dur_label",
            "component": "Text",
            "text": "视频时长",
            "variant": "h4",
        }
    )
    curated = [item for item in (5, 10, 15) if item in caps["durations"]]
    if not curated:
        curated = [caps["durations"][0]]
    duration_options = [{"value": "", "label": "智能"}]
    for item in curated:
        option: dict[str, Any] = {"value": str(item), "label": f"{item} s"}
        if price is not None:
            option["desc"] = f"≈¥{price * item:.2f}"
        duration_options.append(option)
    _add(
        {
            "id": "dur_pick",
            "component": "ChoicePicker",
            "value": {"path": "/form/duration"},
            "options": duration_options,
        }
    )

    # —— 字幕 / 口播 ——
    _add(
        {
            "id": "sub_switch",
            "component": "Switch",
            "label": "需要字幕（生成 .srt）",
            "checked": {"path": "/form/subtitles"},
        }
    )
    _add(
        {
            "id": "sub_note",
            "component": "Text",
            "text": "P1 只产出 .srt 字幕文件，暂不烧制进画面；资讯视频建议勾选。",
            "variant": "caption",
        }
    )
    _add(
        {
            "id": "script_field",
            "component": "TextArea",
            "label": "口播文案（可留空）",
            "value": {"path": "/form/script"},
            "rows": 3,
        }
    )
    _add(
        {
            "id": "script_note",
            "component": "Text",
            "text": "P1 存为旁白稿并写进生成提示，语音合成在 P2。",
            "variant": "caption",
        }
    )

    # —— 动作行 ——
    context = [
        {"key": key, "value": {"path": f"/form/{key}"}}
        for key in form
    ]
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
            "action": {"name": "video_create", "context": context},
        }
    )
    _add(
        {
            "id": "cancel",
            "component": "Button",
            "variant": "ghost",
            "text": "取消",
            "action": {"name": "cancel"},
        }
    )

    surface_id = str(arguments.get("surface_id") or SURFACE_ID)
    surface = {
        "surfaceId": surface_id,
        "title": "视频参数",
        "actions": ["video_create"],
        "components": components,
        "data": {
            "form": form,
            "provider": provider,
            "price_per_second": price,
            "capabilities": {
                "supports_last_frame": bool(caps["supports_last_frame"]),
                "durations": list(caps["durations"]),
                "resolutions": list(caps["resolutions"]),
                "ratios": list(caps["ratios"]),
            },
        },
    }
    return {"surface": surface, "surface_id": surface_id, "provider": provider}


def _active_entry(settings: dict[str, Any]) -> dict[str, Any]:
    from app.config import normalize_media_models

    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "video"
    ]
    return next((entry for entry in entries if entry["active"]), entries[0] if entries else None) or {}


def _price_per_second(options: dict[str, Any]) -> float | None:
    raw = options.get("price_per_second")
    try:
        price = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _default_duration(options: dict[str, Any], caps: dict[str, Any]) -> int:
    """默认时长：条目配置 > 5s（有则用）> 最短档（MiniMax 4s，035 §11 成本护栏）。"""
    raw = options.get("duration")
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = None
    if value is not None and value in caps["durations"]:
        return value
    return 5 if 5 in caps["durations"] else caps["durations"][0]


def _default_resolution(options: dict[str, Any], caps: dict[str, Any]) -> str:
    raw = str(options.get("resolution") or "")
    return raw if raw in caps["resolutions"] else caps["resolutions"][0]


def _default_ratio(options: dict[str, Any], caps: dict[str, Any]) -> str:
    raw = str(options.get("aspect_ratio") or "")
    return raw if raw in caps["ratios"] else ""


@register_tool(
    "video_brief",
    "生成视频前先弹「视频参数」面板让用户确认：素材来源（自定义/网络抓取）/ 首尾帧 / "
    "比例 / 分辨率 / 时长 / 字幕 / 口播。**何时调用**：用户想生成视频但没说清比例或"
    "时长任一项 → 先调本工具，不要直接猜参数生成；用户已明确说了比例和时长，或收到"
    " video_create 回流 → 直接调 video_generate，不要再弹卡。",
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
class VideoBriefAdapter(ToolAdapter):
    """只出面板、不生成。"""

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
            "✓ 已弹出视频参数面板（素材来源 / 首尾帧 / 比例 / 分辨率 / 时长）。"
            "收到 video_create 回流后按参数调用 video_generate：参数以面板值为准，"
            "不要二次确认；素材来源=网络抓取时，先 web_fetch 提炼正文再生成。"
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
                "actionNames": ["video_create"],
            },
        )


def surface_from_args(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """落库回放：入参 → 面板 IR（flight_board / image_brief 同约定）。"""
    try:
        return prepare(arguments or {})["surface"]
    except Exception:  # noqa: BLE001 - 落库不得因面板异常而失败
        return None
