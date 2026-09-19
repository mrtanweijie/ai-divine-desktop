"""把库存记录整理成库位清单。"""

from inventory.schema import field


def locations(records: list[dict]) -> list[str]:
    out = []
    for record in records:
        if field(record, "quantitiy") <= 0:
            continue
        out.append(f"{field(record, 'sku')} @ {field(record, 'location')}")
    return out
