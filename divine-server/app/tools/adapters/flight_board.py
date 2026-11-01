"""flight_board — 机票查询/比价面板（A2UI 出站）。

和 ``render_ui`` 的分工（033 实施补充）：

* ``render_ui`` 让**模型**产出中立 IR —— 灵活，但会漏画、画错、画丑；
* ``flight_board`` 的 IR 由**服务端确定性构建** —— 同一份报价永远渲染出同一块面板，
  用户改条件点「重新查价」后按同一 ``surfaceId`` 原地刷新（028 的 live surface 语义）。

面板承担三件事，且都不依赖模型算：

1. **条件回填**：出发城市 / 目的地范围 / 去程 / 返程 / 预算 / 只看直飞，
   全部绑定 ``data.conditions``，动作 ``flight_search`` 带上下文回流；
2. **±N 天推荐**：``planner.recommend`` 给出的候选（同一趟往返优先）；
3. **请假方案**：每个候选都带「请几天假 / 连休几天」，并在摘要里给最近的假期。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..flight import calendar_cn, planner
from ..flight.compare import format_duration, format_price
from ..registry import register_tool
from ..ui.catalog import MAX_SURFACE_CHARS
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

DESCRIPTION = """渲染机票查询与比价面板（面板本身就是交互界面，不要在正文重复表格数据）。

何时调用：用户要查/比价/收集机票，或要改日期、目的地、预算后再查一次。
输入两份数据：
- conditions：出发城市、目的地范围、去程/返程日期、预算、是否只看直飞（用户没说就留空/默认）
- rows：已经抓到的报价数组，每行 {to, depart, ret?, price, currency?, airline, direct, dep_time?,
  arr_time?, duration?, source?, url?}；ret 有值表示这是**往返总价**，为空表示单程（服务端会把
  同航司去+返两段拼成往返）。价格不会算错——换算汇率、去重、排序、请假天数都由服务端做，
  你只需要**如实把抓到的数字填进来**，不要自己算总价或换算。
  有外币报价时先调 `fx_rates` 刷新汇率缓存，这里读的是同一份，不用写死常数。

面板包含：可编辑条件、±N 天推荐（默认前后 3 天）、请假天数/连休天数、来源比价，
以及围绕最近假期的**拼假方案**（如「10/1–10/10 请 2 天休 10 天」）。
假期数据官方已公布就用官方；**未公布年份按近年规律推断**，面板会带
「以国务院通知为准」的提示——正文转述时必须保留这个限定，不要说成官方安排。
用户点「重新查价」会带着面板里的条件回流，此时按新条件重新抓价后再调一次本工具，
surfaceId 保持不变即可原地刷新，不要新开面板。"""

_WINDOW_DEFAULT = 3

#: 面板最多展示的候选数（Table 上限 200，但人看不了那么多）。
_MAX_ROWS = 20


def _conditions_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "from_city": {"type": "string", "description": "出发城市，如 上海"},
            "to_scope": {
                "type": "string",
                "description": "目的地范围：任意低价 / 国内热门 / 自列清单（如 成都、三亚）",
            },
            "depart_date": {"type": "string", "description": "去程日期 YYYY-MM-DD"},
            "return_date": {"type": "string", "description": "返程日期 YYYY-MM-DD；单程留空"},
            "budget": {"type": "number", "description": "价格上限（元）"},
            "direct_only": {"type": "boolean", "description": "只看直飞"},
            "window": {
                "type": "integer",
                "description": f"日期前后几天参与比价，默认 {_WINDOW_DEFAULT}",
            },
        },
        "required": ["from_city", "depart_date"],
    }


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "conditions": _conditions_schema(),
            "rows": {
                "type": "array",
                "description": "抓到的报价行；往返用 ret 字段表示返程日期，price 填往返总价",
                "items": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "depart": {"type": "string"},
                        "ret": {"type": "string"},
                        "price": {"type": ["number", "string"]},
                        "currency": {"type": "string"},
                        "airline": {"type": "string"},
                        "direct": {"type": ["boolean", "string"]},
                        "dep_time": {"type": "string"},
                        "arr_time": {"type": "string"},
                        "duration": {"type": ["string", "number"]},
                        "source": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["to", "depart", "price"],
                },
            },
            "title": {"type": "string", "description": "面板标题；不填按城市自动生成"},
            "surface_id": {
                "type": "string",
                "description": "面板 id，默认 flight-board；要原地刷新必须复用同一个",
            },
        },
        "required": ["conditions", "rows"],
    }


def _fmt_leave(leave: dict[str, Any] | None) -> str:
    if not leave or not leave.get("ok"):
        return "—"
    days = leave.get("leave_days", 0)
    return "全假期" if days == 0 else f"{days} 天"


def _fmt_rest(leave: dict[str, Any] | None) -> str:
    if not leave or not leave.get("ok"):
        return "—"
    return f"{leave.get('rest_days', 0)} 天"


def build_surface(
    *,
    surface_id: str,
    title: str,
    conditions: dict[str, Any],
    picks: list[dict[str, Any]],
    note: str,
    holiday_text: str,
    leave_plans: list[dict[str, Any]] | None = None,
    estimated: bool = False,
) -> dict[str, Any]:
    """确定性构建中立 IR（可单测，不依赖网络）。"""
    data_conditions = {
        "from_city": str(conditions.get("from_city") or ""),
        "to_scope": str(conditions.get("to_scope") or ""),
        "depart_date": str(conditions.get("depart_date") or ""),
        "return_date": str(conditions.get("return_date") or ""),
        "budget": conditions.get("budget"),
        "direct_only": bool(conditions.get("direct_only")),
    }

    rows = [
        {
            "to": pick["to"],
            "depart": pick["depart"],
            "ret": pick.get("ret") or "—",
            "price": format_price(pick),
            "direct": "直飞" if pick.get("direct") else "经停",
            "leave": _fmt_leave(pick.get("leave")),
            "rest": _fmt_rest(pick.get("leave")),
            "source": pick.get("source") or "—",
        }
        for pick in picks[:_MAX_ROWS]
    ]

    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "Column",
            "gap": "md",
            # 标题由前端用 surface.title 渲染在面板头部，这里不要再放 Text（否则两个标题）
            "children": ["cond1", "cond2", "cond3", "ops", "div", "summary"],
        },
        {"id": "cond1", "component": "Row", "gap": "sm", "children": ["from_city", "to_scope"]},
        {
            "id": "from_city",
            "component": "TextField",
            "label": "出发城市",
            "value": {"path": "/conditions/from_city"},
            "placeholder": "如 上海",
            "required": True,
        },
        {
            "id": "to_scope",
            "component": "TextField",
            "label": "目的地范围",
            "value": {"path": "/conditions/to_scope"},
            "placeholder": "任意低价 / 国内热门 / 成都、三亚",
        },
        {"id": "cond2", "component": "Row", "gap": "sm", "children": ["depart", "ret"]},
        {
            "id": "depart",
            "component": "TextField",
            "label": "去程",
            "value": {"path": "/conditions/depart_date"},
            "placeholder": "YYYY-MM-DD",
            "required": True,
        },
        {
            "id": "ret",
            "component": "TextField",
            "label": "返程",
            "value": {"path": "/conditions/return_date"},
            "placeholder": "单程留空",
        },
        {"id": "cond3", "component": "Row", "gap": "sm", "children": ["budget", "direct"]},
        {
            "id": "budget",
            "component": "NumberField",
            "label": "预算上限",
            "value": {"path": "/conditions/budget"},
            "min": 0,
            "step": 100,
            "unit": "元",
        },
        {
            "id": "direct",
            "component": "Switch",
            "label": "只看直飞",
            "checked": {"path": "/conditions/direct_only"},
        },
        {"id": "ops", "component": "Row", "gap": "sm", "children": ["search"]},
        {
            "id": "search",
            "component": "Button",
            "variant": "primary",
            "text": "重新查价",
            "action": {
                "name": "flight_search",
                "context": [
                    {"key": "from_city", "value": {"path": "/conditions/from_city"}},
                    {"key": "to_scope", "value": {"path": "/conditions/to_scope"}},
                    {"key": "depart_date", "value": {"path": "/conditions/depart_date"}},
                    {"key": "return_date", "value": {"path": "/conditions/return_date"}},
                    {"key": "budget", "value": {"path": "/conditions/budget"}},
                    {"key": "direct_only", "value": {"path": "/conditions/direct_only"}},
                ],
            },
        },
        {"id": "div", "component": "Divider"},
        {"id": "summary", "component": "Text", "text": note, "variant": "body", "tone": "primary"},
    ]

    if holiday_text:
        components.append(
            {"id": "holiday", "component": "Text", "text": holiday_text, "variant": "caption"}
        )
        components[0]["children"].append("holiday")

    if leave_plans:
        plan_text = "拼假方案：" + "；".join(
            f"{plan['range']} {plan['headline']}" for plan in leave_plans[:3]
        )
        components.append(
            {"id": "plans", "component": "Text", "text": plan_text, "variant": "body"}
        )
        components[0]["children"].append("plans")
        if estimated:
            components.append(
                {
                    "id": "plan_note",
                    "component": "Text",
                    "text": "该年份放假安排尚未公布，以上按近年规律推断，以国务院通知为准。",
                    "variant": "caption",
                    "tone": "warning",
                }
            )
            components[0]["children"].append("plan_note")

    if rows:
        components.append(
            {
                "id": "picks",
                "component": "Table",
                "maxHeight": 320,
                "columns": [
                    {"key": "to", "title": "目的地"},
                    {"key": "depart", "title": "去程"},
                    {"key": "ret", "title": "返程"},
                    {"key": "price", "title": "价格"},
                    {"key": "direct", "title": "直飞"},
                    {"key": "leave", "title": "请假"},
                    {"key": "rest", "title": "连休"},
                    {"key": "source", "title": "来源"},
                ],
                "rows": {"path": "/picks"},
            }
        )
        components[0]["children"].append("picks")

    return {
        "surfaceId": surface_id,
        "title": title,
        "actions": ["flight_search"],
        "components": components,
        "data": {"conditions": data_conditions, "picks": rows},
    }


def prepare(arguments: dict[str, Any]) -> dict[str, Any]:
    """从工具入参算出面板与推荐结果（**纯函数**：无 IO、无网络）。

    实时渲染（``run``）与回合收尾的落库回放（``state/persistence.py``）共用这一份，
    保证「当时画出来的」和「重放出来的」是同一块面板，不会两处逻辑各自漂移。
    """
    arguments = arguments or {}
    conditions = arguments.get("conditions") or {}
    rows = arguments.get("rows") or []
    if not isinstance(conditions, dict):
        raise ToolExecutionError("conditions 必须是对象")
    if not isinstance(rows, list):
        raise ToolExecutionError("rows 必须是数组")

    from_city = str(conditions.get("from_city") or "").strip()
    depart = str(conditions.get("depart_date") or "").strip()
    if not from_city or not depart:
        raise ToolExecutionError("conditions 至少要给 from_city 与 depart_date")

    window = conditions.get("window")
    window = int(window) if isinstance(window, (int, float)) and window > 0 else _WINDOW_DEFAULT
    budget = conditions.get("budget")
    budget = float(budget) if isinstance(budget, (int, float)) and budget > 0 else None

    result = planner.recommend(
        rows,
        depart=depart,
        ret=conditions.get("return_date"),
        window=window,
        budget=budget,
        direct_only=bool(conditions.get("direct_only")),
    )

    surface_id = str(arguments.get("surface_id") or "flight-board")
    title = str(arguments.get("title") or f"{from_city} 机票 · ±{window} 天比价")
    context = result.get("holiday_context")
    # 用户给的日期先做单日判定：是假期第几天 / 调休 / 周末 / 工作日。
    # 官方已公布的年份这里不会出现「推断」字样，未公布年份才会带免责后缀。
    selected = calendar_cn.resolve_date(depart)
    parts: list[str] = []
    if selected.get("ok"):
        parts.append(selected["text"])
    if context:
        parts.append(f"假期参考：{context['text']}")

    surface = build_surface(
        surface_id=surface_id,
        title=title,
        conditions=conditions,
        picks=result["candidates"],
        note=result["note"],
        holiday_text="；".join(parts),
        leave_plans=result.get("leave_options") or [],
        estimated=bool((result.get("holiday_context") or {}).get("estimated")),
    )
    return {
        "surface": surface,
        "result": result,
        "window": window,
        "surface_id": surface_id,
    }


def surface_from_args(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """落库回放用：入参 → 面板 IR；算不出来返回 None（落库不得因此失败）。"""
    try:
        return prepare(arguments)["surface"]
    except Exception:  # noqa: BLE001
        return None


@register_tool("flight_board", DESCRIPTION, _schema())
class FlightBoardAdapter(ToolAdapter):
    """把报价行渲染成「条件 + 推荐 + 请假方案 + 比价」面板。"""

    category = "ui"
    timeout = 20

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
        result = prepared["result"]
        window = prepared["window"]
        surface_id = prepared["surface_id"]

        validation = validate_ui_surface(surface)
        if not validation.ok:
            first = validation.errors[0] if validation.errors else None
            raise ToolExecutionError(
                f"面板构建失败（{first.path}）：{first.message}"
                if first
                else "面板构建失败：校验未通过"
            )

        normalized = validation.normalized or surface
        if len(json.dumps(normalized, ensure_ascii=False)) > MAX_SURFACE_CHARS:
            raise ToolExecutionError("面板体积超限，请减少候选数量或缩短备注。")

        messages = to_messages(normalized)
        picked = len(result["candidates"])
        note = (
            f"✓ 已渲染机票面板（{picked} 个候选，±{window} 天）。"
            "面板已呈现给用户，正文只给结论与下一步建议，不要复述表格。"
        )
        if result["dropped"]:
            note += f" 有 {len(result['dropped'])} 行报价因字段缺失被跳过。"

        return ToolResult(
            success=True,
            message=note,
            content=json.dumps(
                {
                    "success": True,
                    "surfaceId": surface_id,
                    "candidates": picked,
                    "best": (
                        {
                            "to": result["best"]["to"],
                            "depart": result["best"]["depart"],
                            "ret": result["best"].get("ret"),
                            "price_cny": result["best"]["price_cny"],
                            "leave_days": (result["best"].get("leave") or {}).get("leave_days"),
                        }
                        if result["best"]
                        else None
                    ),
                    "note": result["note"],
                    "leaveOptions": [
                        {
                            "range": plan["range"],
                            "leaveDays": plan["leave_days"],
                            "totalDays": plan["total_days"],
                            "headline": plan["headline"],
                            "estimated": plan["estimated"],
                        }
                        for plan in (result.get("leave_options") or [])
                    ],
                },
                ensure_ascii=False,
            ),
            data={
                "uiSurface": normalized,
                "a2uiMessages": messages,
                "surfaceId": surface_id,
                "actionNames": ["flight_search"],
            },
        )


__all__ = ["FlightBoardAdapter", "build_surface", "calendar_cn"]
