"""导出格式分发。"""

from inventory import Inventory


def export(inv: Inventory, fmt: str) -> str:
    if fmt == "json":
        return inv.to_json()
    raise ValueError(f"unsupported format: {fmt}")
