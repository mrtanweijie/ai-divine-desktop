"""弃程票（甩尾）识别：票面终点更远、在真实目的地中转时下机，常常更便宜。

两种典型形态（本质同一条规则：**弃掉的必须是这张票的最后一程**，后面没有航段可作废）：

例 1（去程方向）：目的地成都，直飞 ¥1200；「上海 → 成都 → 拉萨」只要 ¥700 —— 在成都下机。
例 2（回程方向，最常见）：去程正常飞清迈，回程买「清迈 → 上海 → 南京」¥900，
     在上海下机、弃掉上海→南京；而「清迈 → 上海」正常单程要 ¥1400。
     此时行级 ``from`` 是清迈，不能用 ``conditions.from_city``（上海）去描述这趟票。

三条边界（写清是为了不被误用）：

1. **弃程的那张票必须是单程票**。往返票是一个合同下的多张顺序客票联：放弃去程尾段即该联 no-show，
   航司会把后续航段一并作废（**含回程**），所以带 ``ret`` 的行一律不提升，仍留在主列表里当普通报价。
   注意「往返行程」不等于「往返票」：去程买一张弃程单程 + 回程另买正常单程是可行的，
   本模块照样识别——被拒的只是往返票本身。
2. **航段是事实，不是推断**。``via`` / ``skip_at`` 只能由模型在页面上真看到才填；
   本模块不做任何航段猜测。拿不到航段 → 就是普通报价。
3. **有尾段才叫弃程**。下发下机城市与票面终点相同（或票面终点缺失）时没有尾段可甩，
   留在主列表。

风险提示文案也在这里定义，面板与正文共用同一句，避免两处口吻不一致。
"""

from __future__ import annotations

from typing import Any, Iterable

from .compare import format_price, normalize_offer

#: 面板最多给出的弃程候选数（再多就没法看了）。
MAX_HIDDEN = 3

#: 弃程票的代价说明——面板副标题与正文转述都用这一句。
#: 注意：面板 Text 是纯文本，不要写 Markdown 记号。
HIDDEN_RISK_NOTE = (
    "弃程票限制：必须是单程票（往返票弃尾段会作废整张，含回程）；"
    "不能托运行李（行李会跟着飞到票面终点）；"
    "航司条款通常禁止弃程，可能被要求补差价或拒绝承运；值机只办到中转点。请自行评估风险。"
)


def _pick_skip_city(offer: dict[str, Any], targets: Iterable[str]) -> str:
    """确定「在哪下机」：显式 skip_at 优先，其次取 via 里出现的真实目的地。"""
    explicit = str(offer.get("skip_at") or "").strip()
    if explicit:
        return explicit
    destination = str(offer.get("to") or "").strip()
    for target in targets:
        name = str(target or "").strip()
        if name and name != destination and name in offer.get("via", []):
            return name
    return ""


def _cheapest_normal(
    offers: list[dict[str, Any]], city: str, depart: str, origin: str
) -> float | None:
    """同一出发城市、同一出发日、到 ``city`` 的最便宜**普通单程**票价（用于算「省多少」）。

    行级 ``from`` 缺省时按同一起点处理——正常报价行的起点就是 ``conditions.from_city``。
    """
    prices = [
        offer["price_cny"]
        for offer in offers
        if offer["to"] == city
        and not offer["ret"]
        and offer["depart"] == depart
        and (offer["from"] or origin) == origin
    ]
    return min(prices) if prices else None


def _flown_label(offer: dict[str, Any], skip_city: str, origin: str) -> str:
    """「实际乘坐」的航段串：多程行程把前序航段一起带上，别只显示最后一段。"""
    legs = offer.get("legs") or []
    if len(legs) >= 2:
        parts = [f"{leg['from']}→{leg['to']}" for leg in legs[:-1]]
        parts.append(f"{legs[-1]['from']}→{skip_city}")
        return " · ".join(parts)
    return f"{origin} → {skip_city}" if origin else skip_city


def split(
    rows: Iterable[dict[str, Any]],
    *,
    from_city: str,
    targets: Iterable[str] = (),
    limit: int = MAX_HIDDEN,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把原始报价行分成 ``(主列表行, 弃程候选)``。

    主列表行保持**原始 dict**（``planner.recommend`` 会自己归一，避免两套口径）；
    弃程候选是已经算好展示字段的扁平对象，可直接进面板表格。
    """
    target_list = [str(item or "").strip() for item in targets]
    main_rows: list[dict[str, Any]] = []
    promoted: list[tuple[dict[str, Any], dict[str, Any]]] = []  # (原始行, 归一结果)

    for row in rows:
        offer, _reason = normalize_offer(row) if isinstance(row, dict) else (None, None)
        if offer is None:
            main_rows.append(row)
            continue
        skip_city = _pick_skip_city(offer, target_list)
        # 往返**票**不提升（顺序客票联，弃尾段会作废回程）；多程行程（legs）的尾段本来就是最后一程，
        # 弃掉不影响任何前序航段，所以放行。
        usable = (
            bool(skip_city)
            and skip_city != offer["to"]
            and (not offer["ret"] or len(offer.get("legs") or []) >= 2)
        )
        if not usable:
            main_rows.append(row)
            continue
        promoted.append((row, offer))

    # 主列表里的普通报价也归一一份，用来算「比直飞省多少」
    normal_offers = [
        offer
        for offer in (normalize_offer(row)[0] for row in main_rows if isinstance(row, dict))
        if offer is not None
    ]

    hidden: list[dict[str, Any]] = []
    for _row, offer in promoted:
        skip_city = _pick_skip_city(offer, target_list)
        origin = offer["from"] or from_city
        # 多程行程的总价没有可比的「单段普通价」，硬算会给出误导性的省额 → 留空
        baseline = (
            None
            if len(offer.get("legs") or []) >= 2
            else _cheapest_normal(normal_offers, skip_city, offer["depart"], origin)
        )
        save = round(baseline - offer["price_cny"], 2) if baseline is not None else None
        hidden.append(
            {
                "skip_at": skip_city,
                "route": _flown_label(offer, skip_city, origin),
                "to": offer["to"],
                "tail": f"{skip_city} → {offer['to']}",
                "depart": offer["depart"],
                "airline": offer["airline"],
                "price": format_price(offer),
                "price_cny": offer["price_cny"],
                "save": f"省 ¥{int(round(save))}" if save and save > 0 else "—",
                "save_cny": save if save and save > 0 else None,
                "source": offer["source"],
                "url": offer["url"],
            }
        )

    # 省得多的排前面；没有对比基准的排最后，再按价格升序
    hidden.sort(key=lambda item: (-(item["save_cny"] or 0), item["price_cny"]))
    return main_rows, hidden[: max(1, limit)]
