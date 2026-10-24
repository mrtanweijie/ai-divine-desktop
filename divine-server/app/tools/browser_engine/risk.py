"""风险分级（031 §6.1）：intent 标注 + 高风险词典兜底。

三层判定中的 1/2 层在这里落地：
1. 工具静态级——adapter schema 层面体现（read_page 恒只读，click/fill 依赖标注）；
2. 动作标注——`intent` 参数（read / reversible / irreversible）；
3. 高风险词典兜底——目标元素名称命中词典 → 无视标注一律按 irreversible。

会话内 `confirmed` 标志（由 web_task(confirmed=True) 委派设置）是 irreversible
动作的唯一放行条件；未确认的委派段里 irreversible 动作直接拒绝，
对应设计 031 §3 "不可逆动作必须隔离在独立委派段"。
"""

from __future__ import annotations

from typing import Any

# 不可逆动作词典（目标元素 role+name 命中即按 irreversible 处理，无视 intent 标注）。
# 命中判定为"元素名称包含词条"，小写匹配；中英并列。
IRREVERSIBLE_TERMS: tuple[str, ...] = (
    "提交订单",
    "确认下单",
    "下单",
    "支付",
    "付款",
    "结算",
    "立即购买",
    "购买",
    "买入",
    "转账",
    "充值",
    "提现",
    "删除",
    "移除",
    "清空",
    "撤销",
    "取消订单",
    "退款",
    "申请售后",
    "发送",
    "发布",
    "提交",
    "授权",
    "同意并继续",
    "退出登录",
    "注销",
    "checkout",
    "pay now",
    "place order",
    "purchase",
    "delete",
    "remove",
    "send",
    "publish",
    "submit",
    "authorize",
    "sign out",
    "log out",
)

# 凭据类输入禁令（031 §6.4：禁止输入任何凭据/验证码/API key）。
# 命中字段名/元素名 → fill 一律拒绝，无任何放行路径。
CREDENTIAL_TERMS: tuple[str, ...] = (
    "密码",
    "验证码",
    "口令",
    "pin码",
    "cvv",
    "安全码",
    "card code",
    "password",
    "passwd",
    "pwd",
    "passcode",
    "captcha",
    "otp",
    "verification code",
    "api key",
    "api token",
    "secret",
)

VALID_INTENTS = ("read", "reversible", "irreversible")


def normalize_intent(value: Any) -> str | None:
    """校验模型给的 intent 标注；非法值返回 None（按默认处理并提示）。"""
    if value is None:
        return None
    v = str(value).strip().lower()
    return v if v in VALID_INTENTS else None


def _name_matches(name: str, terms: tuple[str, ...]) -> str | None:
    lowered = (name or "").strip().lower()
    if not lowered:
        return None
    for term in terms:
        if term in lowered:
            return term
    return None


def classify_action(name: str, intent: str | None) -> tuple[str, str | None]:
    """判定动作风险级别，返回 (level, 命中词条)。

    词典兜底优先于 intent 标注；无标注的常规动作默认 reversible
    （导航类点击占绝大多数，全按 irreversible 会把确认卡打穿）。
    """
    hit = _name_matches(name, IRREVERSIBLE_TERMS)
    if hit:
        return "irreversible", hit
    if intent == "irreversible":
        return "irreversible", None
    if intent == "read":
        return "read", None
    return "reversible", None


def credential_hit(field_name: str) -> str | None:
    """fill 目标字段命中凭据词典时返回词条（拒绝输入）。"""
    return _name_matches(field_name, CREDENTIAL_TERMS)


def refusal_payload(message: str, **extra: Any) -> dict[str, Any]:
    """风险拒绝的结构化返回：模型读得到原因与修正方式。

    返回 dict（与 engine 操作层契约一致），序列化由 adapter 层负责。
    """
    return {"success": False, "rejected": True, "message": message, **extra}
