import pytest

from exporters import export
from inventory import Inventory


def make_inv() -> Inventory:
    inv = Inventory()
    inv.add("banana", 12, 3.5)
    inv.add("apple", 3, 1.25)
    return inv


def test_to_csv_header_and_order():
    lines = make_inv().to_csv().splitlines()
    assert lines[0] == "name,qty,price"
    assert lines[1] == "apple,3,1.25"
    assert lines[2] == "banana,12,3.5"


def test_export_csv_dispatch():
    assert export(make_inv(), "csv") == make_inv().to_csv()


def test_export_json_still_works():
    assert '"apple"' in export(make_inv(), "json")


def test_unknown_format_raises():
    with pytest.raises(ValueError):
        export(make_inv(), "xml")
