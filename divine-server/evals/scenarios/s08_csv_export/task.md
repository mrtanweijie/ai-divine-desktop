给库存模块增加 CSV 导出能力：
1) inventory.py 的 Inventory 增加 to_csv() 方法——首行表头 name,qty,price；
   数据行按 name 升序排列；qty 输出整数、price 原样输出；逗号分隔、
   不需要引号转义（数据保证不含逗号）。
2) exporters.py 的 export() 支持 fmt="csv"，直接返回 inv.to_csv() 的结果；
   "json" 分支和未知格式抛 ValueError 的行为保持不变。
