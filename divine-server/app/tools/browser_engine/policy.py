"""域策略包钩子（031 §6.3 / §14.3）——购物包最小版。

从扁平 settings 读取护栏配置（settings_store 的键是扁平的，无点号路径）：
- ``shopping_per_order_cap``   单笔金额上限，默认 200
- ``shopping_monthly_cap``     月度上限，缺省不启用
- ``shopping_policy_domains``  购物包域名列表（逗号分隔子串匹配），默认四大平台

extract 结果经过 :func:`evaluate_shopping_policy` 时：
- 命中购物域名 → 附加 policy 附件（包名、警示、金额护栏判定）；
- 文本含"免密" → 免密警示（031 §14.3：提交订单即扣款的红线补丁）；
- 解析出结算金额且超单笔上限 → guard=block（确认卡阶段必须二次确认/拒绝）。

这是纯函数钩子，不触网、不改 DOM——护栏判定在确认卡前发生。
"""

from __future__ import annotations

import json
import re
from typing import Any

DEFAULT_SHOPPING_DOMAINS = (
    "meituan.com",
    "ele.me",
    "taobao.com",
    "jd.com",
)

DEFAULT_PER_ORDER_CAP = 200

# 结算金额：优先取"应付/合计/实付"附近的数字；退而求其次取第一个 ¥ 金额
_SETTLED_RE = re.compile(r"(?:应付|实付|合计|总计|总额)[^\d¥￥]{0,8}[¥￥]?\s*(\d+(?:\.\d{1,2})?)")
_ANY_PRICE_RE = re.compile(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)")


def _load_settings() -> dict[str, Any]:
    try:
        from ...config import settings_store

        return settings_store.load()
    except Exception:  # noqa: BLE001 — 读不到设置按默认护栏走
        return {}


def shopping_domains() -> tuple[str, ...]:
    raw = str(_load_settings().get("shopping_policy_domains") or "").strip()
    if not raw:
        return DEFAULT_SHOPPING_DOMAINS
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts or DEFAULT_SHOPPING_DOMAINS


def _domain_list(key: str) -> tuple[str, ...]:
    raw = str(_load_settings().get(key) or "").strip()
    return tuple(p.strip().lower() for p in raw.split(",") if p.strip())


def blocked_domain_hit(url: str) -> str | None:
    """用户禁止名单（browser_blocked_domains）：命中返回域名子串。"""
    lowered = (url or "").lower()
    for domain in _domain_list("browser_blocked_domains"):
        if domain and domain in lowered:
            return domain
    return None


def in_confirm_domains(url: str) -> bool:
    """用户每次确认名单（browser_confirm_domains）：变更动作须 confirmed 委派段。"""
    lowered = (url or "").lower()
    return any(domain and domain in lowered for domain in _domain_list("browser_confirm_domains"))


def default_address() -> str:
    return str(_load_settings().get("shopping_default_address") or "").strip()


def per_order_cap() -> float:
    try:
        return float(_load_settings().get("shopping_per_order_cap") or DEFAULT_PER_ORDER_CAP)
    except (TypeError, ValueError):
        return float(DEFAULT_PER_ORDER_CAP)


def match_domain_pack(url: str) -> str | None:
    """返回命中的域策略包名；目前只有 shopping。"""
    lowered = (url or "").lower()
    if any(domain in lowered for domain in shopping_domains()):
        return "shopping"
    return None


def evaluate_shopping_policy(url: str, text: str) -> dict[str, Any] | None:
    """对一次 extract/快照文本做购物包判定；未命中域名返回 None。"""
    if match_domain_pack(url) != "shopping":
        return None
    warnings: list[str] = []
    guard: dict[str, Any] | None = None

    if "免密" in text:
        warnings.append(
            "该账户页面出现「免密」字样：免密支付账户提交订单即扣款，"
            "提交动作必须位于 confirmed=true 的委派段，且确认卡需展示支付方式"
        )

    amount: float | None = None
    match = _SETTLED_RE.search(text)
    if match:
        amount = float(match.group(1))
    else:
        any_price = _ANY_PRICE_RE.search(text)
        if any_price:
            amount = float(any_price.group(1))
    if amount is not None:
        cap = per_order_cap()
        guard = {
            "amount": amount,
            "per_order_cap": cap,
            "verdict": "block" if amount > cap else "pass",
        }
        if guard["verdict"] == "block":
            warnings.append(
                f"结算金额 {amount} 超过单笔上限 {cap}：确认卡升级为二次确认，或拒绝提交"
            )

    # 地址校验（031 §14.3）：结算文本出现"收货地址"且与记忆默认地址明显不一致时警示
    preferred = default_address()
    if preferred and ("收货地址" in text or "选择地址" in text):
        if preferred[:6] not in text:
            warnings.append(
                f"收货地址与默认地址（{preferred[:12]}…）不一致：确认卡必须展示完整地址并请用户核对"
            )

    return {
        "domain_pack": "shopping",
        "warnings": warnings,
        "amount_guard": guard,
    }


def policy_attachment(url: str, text: str) -> str | None:
    """给 extract/快照结果附带的策略 JSON 文本；无命中返回 None。"""
    payload = evaluate_shopping_policy(url, text)
    if payload is None:
        return None
    return json.dumps({"policy": payload}, ensure_ascii=False)
