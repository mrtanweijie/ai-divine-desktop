from pager import paginate, page_count

ITEMS = list(range(25))


def test_first_page():
    assert paginate(ITEMS, page=1, per_page=10) == list(range(10))


def test_second_page():
    assert paginate(ITEMS, page=2, per_page=10) == list(range(10, 20))


def test_last_partial_page():
    assert paginate(ITEMS, page=3, per_page=10) == [20, 21, 22, 23, 24]


def test_out_of_range_page():
    assert paginate(ITEMS, page=9, per_page=10) == []


def test_page_count():
    assert page_count(ITEMS, per_page=10) == 3


def test_invalid_args():
    assert paginate(ITEMS, page=0, per_page=10) == []
