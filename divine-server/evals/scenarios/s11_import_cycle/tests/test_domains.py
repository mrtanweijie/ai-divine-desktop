def test_order_and_payment_link():
    from orders import Order
    from payments import Payment, PaymentStatus

    order = Order("o-1", 9.9)
    assert order.status is PaymentStatus.PENDING
    payment = Payment(order, 9.9)
    assert payment.order is order


def test_status_enum_values():
    from payments import PaymentStatus

    assert PaymentStatus.PAID.value == "paid"


def test_order_total_unaffected():
    from totals import order_total

    assert order_total([{"price": 2.5, "qty": 4}]) == 10.0
