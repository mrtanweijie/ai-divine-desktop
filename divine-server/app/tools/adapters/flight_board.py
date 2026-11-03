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
from ..flight import calendar_cn, hidden_city, planner
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

**弃程（甩尾）票**：目的地明确、但直飞明显贵时，顺手查「票面终点更远、在该目的地中转」的航班
（例：去成都，查上海→成都→拉萨）。找到就：`to` 填票面终点（拉萨）、`via` 填 ["成都"]、
`skip_at` 填 成都。服务端会自动把它移出主列表、单列到「弃程票」一栏并算出比直飞省多少，
面板自带风险提示；正文转述时**必须保留**「弃程的票必须是单程（往返票弃尾段会作废整张，含回程）/
不能托运行李 / 航司条款可能禁止弃程」。
**回程方向同样适用、往往更划算**：去程正常飞清迈，回程查「清迈→上海→南京」，在上海下机、
弃掉最后一程（后面没有航段，不影响前面任何一段）——这种行必须填 `from`（清迈），
否则会被当成从出发城市起飞的票而描述错。
注意「往返行程」不等于「往返票」：往返需求下，去程买一张弃程单程、回程另买正常单程是可行的——
只要该行本身是单程（`ret` 为空）就会识别；带 `ret` 的往返票则不提升。
`via` 与 `skip_at` 只能来自真实页面——抓不到航段就别填，不要自己拼航线。

**多程（open-jaw / 多段）**：用户「去 A 回 B」（进出城市不同）或需要中间停一站时，走 OTA 的
「多程」一次查整程总价——通常比拆成两个单程便宜。传 `conditions.trip_type="multi_city"` 与
`conditions.legs=[{from,to,date},…]`；每条报价行也用 `legs` 表达整程（**一行 = 一个完整行程**，
`price` 是全程总价，不必再填 `to`/`depart`）。面板会自动切到「航段 / 全程价」列。
不要把它拆成两个单程去比较，也不要把多程总价填进单程行。
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
            "target_city": {
                "type": "string",
                "description": (
                    "用户真正的目的地城市（单值）。用于识别「票买到更远、在该城市中转」的弃程票："
                    "报价行里 via 含该城市且票面终点不同，就自动单列一栏。用户没明确指定目的地时留空。"
                ),
            },
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
            "trip_type": {
                "type": "string",
                "enum": ["one_way", "round_trip", "multi_city"],
                "description": (
                    "行程形态。多程（open-jaw / 多段）用 multi_city 并同时给 legs；"
                    "不填时服务端按「有 legs → 多程 / 有 return_date → 往返 / 否则单程」推断。"
                ),
            },
            "legs": {
                "type": "array",
                "description": (
                    "多程行程的航段，按顺序 [{from,to,date}]，如 "
                    "[{from:上海,to:清迈,date:2026-12-01},{from:清迈,to:南京,date:2026-12-08}]。"
                    "OTA 的「多程」一次给整程总价，通常比两个单程便宜（open-jaw 尤其明显）。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "date": {"type": "string"},
                    },
                    "required": ["from", "to"],
                },
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
                        "from": {
                            "type": "string",
                            "description": (
                                "该行的出发城市，缺省 = conditions.from_city。"
                                "**返程方向的票必须填**（如回程「清迈→上海→南京」填 清迈），"
                                "否则弃程候选会被误描述成从出发城市起飞。"
                            ),
                        },
                        "depart": {"type": "string"},
                        "ret": {"type": "string"},
                        "via": {
                            "type": ["array", "string"],
                            "items": {"type": "string"},
                            "description": (
                                "该票的中转/经停城市，按顺序，不含出发地与票面终点；"
                                "如 ['成都']。**只在页面上真看到航段时才填**，抓不到就留空——"
                                "服务端靠它识别弃程票，编造会误导用户。"
                            ),
                        },
                        "skip_at": {
                            "type": "string",
                            "description": (
                                "弃程票：计划下机的城市（用户真实目的地，且 != to）。"
                                "填了它服务端会把该行移出主列表、单列到「弃程票」一栏并算省多少。"
                            ),
                        },
                        "legs": {
                            "type": "array",
                            "description": (
                                "多程报价的整程航段 [{from,to,date}]（一行 = 一个完整行程，price 是全程总价）。"
                                "给了它就不用再填 to/depart，服务端按首末航段推出。"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "date": {"type": "string"},
                                },
                                "required": ["from", "to"],
                            },
                        },
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
    hidden: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """确定性构建中立 IR（可单测，不依赖网络）。"""
    trip_type = str(conditions.get("trip_type") or "").strip()
    multi_city = trip_type == "multi_city"
    data_conditions = {
        "from_city": str(conditions.get("from_city") or ""),
        "to_scope": str(conditions.get("to_scope") or ""),
        "depart_date": str(conditions.get("depart_date") or ""),
        "return_date": str(conditions.get("return_date") or ""),
        "budget": conditions.get("budget"),
        "direct_only": bool(conditions.get("direct_only")),
        "trip_type": trip_type,
        "legs": conditions.get("legs") or [],
    }

    def _legs_label(pick: dict[str, Any]) -> str:
        """多程行的航段串：`上海→清迈 12-01 · 清迈→南京 12-08`。"""
        legs = pick.get("legs") or []
        if not legs:
            return f"{pick.get('from') or conditions.get('from_city') or ''}→{pick['to']}"
        parts = []
        for leg in legs:
            day = f" {leg['date']}" if leg.get("date") else ""
            parts.append(f"{leg['from']}→{leg['to']}{day}")
        return " · ".join(parts)

    def _row_for(pick: dict[str, Any]) -> dict[str, Any]:
        """按行程形态产出**恰好等于列集合**的行对象（多一格都会被 L2 校验判为不一致）。"""
        if multi_city:
            legs = pick.get("legs") or []
            return {
                "legs": _legs_label(pick),
                "price": format_price(pick),
                "stops": "直飞" if len(legs) <= 1 and pick.get("direct") else f"{max(len(legs) - 1, 1)} 次中转",
                "leave": _fmt_leave(pick.get("leave")),
                "rest": _fmt_rest(pick.get("leave")),
                "source": pick.get("source") or "—",
            }
        return {
            "to": pick["to"],
            "depart": pick["depart"],
            "ret": pick.get("ret") or "—",
            "price": format_price(pick),
            "direct": "直飞" if pick.get("direct") else "经停",
            "leave": _fmt_leave(pick.get("leave")),
            "rest": _fmt_rest(pick.get("leave")),
            "source": pick.get("source") or "—",
        }

    rows = [_row_for(pick) for pick in picks[:_MAX_ROWS]]

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
        columns = (
            [
                {"key": "legs", "title": "航段"},
                {"key": "price", "title": "全程价"},
                {"key": "stops", "title": "中转"},
                {"key": "leave", "title": "请假"},
                {"key": "rest", "title": "连休"},
                {"key": "source", "title": "来源"},
            ]
            if multi_city
            else [
                {"key": "to", "title": "目的地"},
                {"key": "depart", "title": "去程"},
                {"key": "ret", "title": "返程"},
                {"key": "price", "title": "价格"},
                {"key": "direct", "title": "直飞"},
                {"key": "leave", "title": "请假"},
                {"key": "rest", "title": "连休"},
                {"key": "source", "title": "来源"},
            ]
        )
        components.append(
            {
                "id": "picks",
                "component": "Table",
                "maxHeight": 320,
                "columns": columns,
                "rows": {"path": "/picks"},
            }
        )
        components[0]["children"].append("picks")

    # 弃程票（甩尾）单独一栏：不混进主列表，避免便宜但有限制的票冲上第一被误点。
    if hidden:
        skip_cities = list(dict.fromkeys(item["skip_at"] for item in hidden))
        components.extend(
            [
                {"id": "hidden_div", "component": "Divider"},
                {
                    "id": "hidden_head",
                    "component": "Text",
                    "text": (
                        f"也可以这样飞：在{'、'.join(skip_cities)}下机的弃程票"
                        f"（票买到更远的城市，尾段不上飞机）"
                    ),
                    "variant": "body",
                    "tone": "primary",
                },
                {
                    "id": "hidden_table",
                    "component": "Table",
                    "maxHeight": 240,
                    "columns": [
                        {"key": "route", "title": "实际乘坐"},
                        {"key": "tail", "title": "弃掉的尾段"},
                        {"key": "depart", "title": "去程"},
                        {"key": "price", "title": "价格"},
                        {"key": "save", "title": "比直飞省"},
                        {"key": "source", "title": "来源"},
                    ],
                    "rows": {"path": "/hidden"},
                },
                {
                    "id": "hidden_note",
                    "component": "Text",
                    "text": hidden_city.HIDDEN_RISK_NOTE,
                    "variant": "caption",
                    "tone": "warning",
                },
            ]
        )
        components[0]["children"].extend(
            ["hidden_div", "hidden_head", "hidden_table", "hidden_note"]
        )

    return {
        "surfaceId": surface_id,
        "title": title,
        "actions": ["flight_search"],
        "components": components,
        "data": {"conditions": data_conditions, "picks": rows, "hidden": hidden or []},
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
    # 多程可以不给 depart_date：日期在第一段航程里
    if not depart:
        first_leg = (conditions.get("legs") or [{}])[0]
        if isinstance(first_leg, dict):
            depart = str(first_leg.get("date") or "").strip()
    if not from_city or not depart:
        raise ToolExecutionError("conditions 至少要给 from_city 与 depart_date（多程可给 legs）")

    window = conditions.get("window")
    window = int(window) if isinstance(window, (int, float)) and window > 0 else _WINDOW_DEFAULT
    budget = conditions.get("budget")
    budget = float(budget) if isinstance(budget, (int, float)) and budget > 0 else None

    # 行程形态：显式优先，否则按「有 legs → 多程 / 有 return_date → 往返 / 其余单程」推断
    trip_type = str(conditions.get("trip_type") or "").strip()
    if not trip_type:
        has_legs = bool(conditions.get("legs")) or any(
            isinstance(row, dict) and (row.get("legs") or row.get("segments"))
            for row in rows
        )
        trip_type = (
            "multi_city" if has_legs else ("round_trip" if conditions.get("return_date") else "one_way")
        )
    conditions = {**conditions, "trip_type": trip_type}

    # 弃程票先分流：主列表只留正常票，甩尾候选单独一栏（判定逻辑见 flight/hidden_city.py）
    target_city = str(conditions.get("target_city") or "").strip()
    main_rows, hidden = hidden_city.split(
        rows,
        from_city=from_city,
        targets=[target_city] if target_city else [],
    )

    result = planner.recommend(
        main_rows,
        depart=depart,
        ret=conditions.get("return_date"),
        window=window,
        budget=budget,
        direct_only=bool(conditions.get("direct_only")),
        trip_type=trip_type,
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

    note = result["note"]
    if hidden:
        if result["candidates"]:
            note += f"；另有 {len(hidden)} 个弃程票更便宜（见下，有限制）"
        else:
            # 单程查询常见：没有正常报价，但弃程票有货——不能让摘要继续说「没有报价」
            note = (
                f"±{window} 天内没有可用的普通报价，"
                f"但找到 {len(hidden)} 个弃程票（见下，有限制）。"
            )

    surface = build_surface(
        surface_id=surface_id,
        title=title,
        conditions=conditions,
        picks=result["candidates"],
        note=note,
        hidden=hidden,
        holiday_text="；".join(parts),
        leave_plans=result.get("leave_options") or [],
        estimated=bool((result.get("holiday_context") or {}).get("estimated")),
    )
    return {
        "surface": surface,
        "result": result,
        "hidden": hidden,
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
