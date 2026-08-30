store.py 的 fetch_data 这个名字不能说明它在做什么，请把它在整个仓库里
重命名为 load_records：包括 store.py 里的函数定义，以及 api.py、
report.py、cache_layer.py 里所有 import 和调用点。
要求：函数行为完全不变，改名后不能再有 fetch_data 残留。
