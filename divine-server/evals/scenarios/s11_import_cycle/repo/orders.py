"""订单领域模型。"""

from payments import PaymentStatus


class Order:
    def __init__(self, order_id: str, amount: float) -> None:
        self.id = order_id
        self.amount = amount
        self.status = PaymentStatus.PENDING

    def paid(self) -> None:
        self.status = PaymentStatus.PAID
