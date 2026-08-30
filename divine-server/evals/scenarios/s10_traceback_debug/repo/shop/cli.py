"""命令行入口：python -m shop 会依次查询 apple、bolt 的库位。"""


def main(args: list[str] | None = None) -> str:
    from shop import warehouse

    args = list(args if args is not None else ["apple", "bolt"])
    out = []
    for item in args:
        out.append(f"{item} -> {warehouse.locaton(item)}")
    return "; ".join(out)
