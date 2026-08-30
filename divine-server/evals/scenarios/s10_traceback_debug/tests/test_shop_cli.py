import pytest


def test_main_returns_locations():
    from shop.cli import main

    assert main(["apple", "bolt"]) == "apple -> A-01; bolt -> C-07"


def test_unknown_item_raises_key_error():
    from shop.cli import main

    with pytest.raises(KeyError):
        main(["ghost"])


def test_warehouse_locate_direct():
    from shop.warehouse import locate

    assert locate("apple") == "A-01"
