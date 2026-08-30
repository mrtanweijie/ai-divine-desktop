"""库存数据模型与导出。"""

import json


class Inventory:
    def __init__(self, items: list[dict] | None = None) -> None:
        # 每个条目: {"name": str, "qty": int, "price": float}
        self.items = list(items or [])

    def add(self, name: str, qty: int, price: float) -> None:
        self.items.append({"name": name, "qty": qty, "price": price})

    def sorted_items(self) -> list[dict]:
        return sorted(self.items, key=lambda item: item["name"])

    def to_json(self) -> str:
        return json.dumps(self.sorted_items(), ensure_ascii=False)
