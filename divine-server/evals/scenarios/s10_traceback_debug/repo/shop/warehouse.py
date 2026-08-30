"""仓库查询。"""

STOCK = {
    "apple": {"qty": 12, "location": "A-01"},
    "bolt": {"qty": 500, "location": "C-07"},
}


def locate(item: str) -> str:
    if item not in STOCK:
        raise KeyError(item)
    return STOCK[item]["location"]
