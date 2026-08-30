"""Simple list pagination helpers."""


def paginate(items: list, page: int = 1, per_page: int = 10) -> list:
    """Return one page of items.

    page starts at 1; out-of-range pages return an empty list.
    """
    if page < 1 or per_page < 1:
        return []
    start = page * per_page
    return items[start : start + per_page]


def page_count(items: list, per_page: int = 10) -> int:
    if per_page < 1:
        return 0
    return (len(items) + per_page - 1) // per_page
