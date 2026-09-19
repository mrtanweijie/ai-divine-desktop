这个库存小工具跑不起来了：执行 `python -m inventory` 直接抛异常，
本来应该打印 "apple @ A-01"（bolt 的库存是 0，会被跳过）。

请找出根因并修好，让 `python -m inventory` 能正常打印库位清单。

`inventory/schema.py` 的字段访问约定不要动——缺字段就该抛 KeyError，
只修真正出问题的那一处。
