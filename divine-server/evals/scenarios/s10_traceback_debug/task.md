这个项目是一个极简的商店查询工具：运行 `python -m shop` 会查询每个商品的库位，
但现在直接崩了，报 AttributeError。请找出根因并修复：
修复后 `python -m shop` 应能打印 "apple -> A-01; bolt -> C-07"，
查询不存在的商品时仍然抛 KeyError，warehouse 模块本身的行为不要动。
