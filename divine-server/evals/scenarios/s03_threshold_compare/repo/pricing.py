TIER_10 = 100.0
TIER_20 = 500.0


def discount_for(total: float) -> float:
    """Return the payable amount after the tiered discount.

    满 100 元（含）打九折，满 500 元（含）打八折。
    """
    if total > TIER_20:
        return round(total * 0.8, 2)
    if total > TIER_10:
        return round(total * 0.9, 2)
    return round(total, 2)
