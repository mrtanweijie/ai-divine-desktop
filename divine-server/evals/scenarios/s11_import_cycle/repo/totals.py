"""与订单/支付无关的金额计算工具。"""


def order_total(items: list[dict]) -> float:
    return round(sum(item["price"] * item["qty"] for item in items), 2)
