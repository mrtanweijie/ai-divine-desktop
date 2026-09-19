import pytest


def test_locations_skips_empty_stock():
    from inventory.report import locations

    records = [
        {"sku": "apple", "quantity": 12, "location": "A-01"},
        {"sku": "bolt", "quantity": 0, "location": "C-07"},
    ]
    assert locations(records) == ["apple @ A-01"]


def test_locations_keeps_all_in_stock():
    from inventory.report import locations

    records = [{"sku": "nut", "quantity": 3, "location": "B-02"}]
    assert locations(records) == ["nut @ B-02"]


def test_schema_field_direct():
    from inventory.schema import field

    assert field({"a": 1}, "a") == 1
    with pytest.raises(KeyError):
        field({"a": 1}, "b")
