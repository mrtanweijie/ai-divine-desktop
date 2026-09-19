"""库存记录的字段访问。"""

FIELDS = ("sku", "quantity", "location")


def field(record: dict, name: str) -> object:
    """按字段名取值；缺字段就抛 KeyError，尽早暴露脏数据。"""
    return record[name]
