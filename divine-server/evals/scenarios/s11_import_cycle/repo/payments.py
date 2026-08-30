"""支付领域模型。"""

import enum

from orders import Order


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class Payment:
    def __init__(self, order: "Order", amount: float) -> None:
        self.order = order
        self.amount = amount
