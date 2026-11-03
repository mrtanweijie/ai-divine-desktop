"""flight_hidden_targets — 主动找弃程：算出「该再查哪几条更远终点的航线」。

只出清单、不抓价：抓价仍由 web_task + OTA 配方完成（033），本工具负责把
「该试哪几条」从经验猜测变成确定性结果（见 ``flight/onward.py``）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolResult
from ..flight import onward
from ..registry import register_tool

DESCRIPTION = """为「主动找弃程票」生成候选航线清单。

给定出发城市与用户**真实目的地**，按方位与距离筛出几个「票面终点更远、可能经该目的地中转」
的城市——这些航线才可能拼出比直飞更便宜的弃程票。

何时调用：用户目的地明确、正常票价偏高，且表示想省钱/看看有没有更便宜的时。
**不要凭感觉编城市**，用本工具给的清单。

拿到清单后：对每条候选航线（`{出发城市}→{候选城市}`）用 web_task 查一次 OTA。
若某条报价的中转城市**正是**用户目的地，就在 flight_board 的 rows 里把
`to` 填票面终点（候选城市）、`via` 填 [目的地]、`skip_at` 填 目的地；
查不到经停就**不要填**——那只是一张普通机票，硬填会误导用户。"""


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "from_city": {
                "type": "string",
                "description": "出发城市（用户所在城市），如 上海",
            },
            "target_city": {
                "type": "string",
                "description": "用户真正的目的地城市，如 成都；中文名或三字码都行",
            },
            "limit": {
                "type": "integer",
                "description": "最多给几个候选（默认 3，别超过 5——每多一条就多一次抓价）",
            },
        },
        "required": ["from_city", "target_city"],
    }


def build_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    """纯函数：入参 → 候选清单（可单测，无 IO）。"""
    from_city = str(arguments.get("from_city") or "").strip()
    target_city = str(arguments.get("target_city") or "").strip()
    if not from_city or not target_city:
        raise ValueError("from_city 与 target_city 都必须给")

    raw_limit = arguments.get("limit")
    limit = int(raw_limit) if isinstance(raw_limit, (int, float)) else 3
    limit = max(1, min(limit, 5))

    origin = onward.resolve_city(from_city)
    target = onward.resolve_city(target_city)
    candidates = onward.onward_candidates(from_city, target_city, limit=limit)

    if origin is None or target is None:
        unknown = from_city if origin is None else target_city
        return {
            "from_city": from_city,
            "target_city": target_city,
            "candidates": [],
            "unknown_city": unknown,
            "how_to": f"「{unknown}」不在坐标表里，无法推算更远终点——直接按正常流程查价即可。",
        }

    how_to = (
        f"对下面每条航线各查一次 OTA；命中条件是「中转城市 = {target}」。"
        f"命中就把该行的 to 填票面终点、via 填 [{target}]、skip_at 填 {target}；"
        "没命中就是普通机票，不要硬填。"
    )
    return {
        "from_city": origin,
        "target_city": target,
        "candidates": candidates,
        "how_to": how_to,
    }


def _format_message(payload: dict[str, Any]) -> str:
    candidates = payload["candidates"]
    if not candidates:
        if payload.get("unknown_city"):
            return payload["how_to"]
        return (
            f"⚠ 从 {payload['from_city']} 出发、以 {payload['target_city']} 为目的地的方向上，"
            "找不到「更远且同向」的城市——这条航线不适合找弃程票，直接按正常报价处理。"
        )
    lines = [
        f"✓ {payload['from_city']} → {payload['target_city']}："
        f"{len(candidates)} 条弃程候选航线（票面终点更远，可能经该目的地中转）"
    ]
    for index, item in enumerate(candidates, start=1):
        lines.append(
            f"{index}. 查 {payload['from_city']}→{item['city']}"
            f"（{item['reason']}）"
        )
    lines.append(payload["how_to"])
    return "\n".join(lines)


@register_tool("flight_hidden_targets", DESCRIPTION, _schema())
class FlightHiddenTargetsAdapter(ToolAdapter):
    """把「该查哪几条更远终点航线」算成清单，供模型去 OTA 实查。"""

    category = "web"
    timeout = 10

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del workspace, locale, progress_callback

        try:
            payload = build_payload(arguments or {})
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc), content=json.dumps({"success": False}))

        return ToolResult(
            success=True,
            message=_format_message(payload),
            content=json.dumps({"success": True, **payload}, ensure_ascii=False),
            data=payload,
        )
