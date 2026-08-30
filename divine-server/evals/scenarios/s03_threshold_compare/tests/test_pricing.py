from pricing import discount_for


def test_exactly_100_gets_10_percent_off():
    assert discount_for(100.0) == 90.0


def test_exactly_500_gets_20_percent_off():
    assert discount_for(500.0) == 400.0


def test_below_first_tier_unchanged():
    assert discount_for(99.99) == 99.99


def test_small_amount_unchanged():
    assert discount_for(80.0) == 80.0


def test_above_second_tier():
    assert discount_for(1000.0) == 800.0
