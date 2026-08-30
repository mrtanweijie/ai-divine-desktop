cache.py 的 FetchCache 缓存键没有把查询参数算进去：同一个 URL 不同参数
（比如 page=1 和 page=2）会互相覆盖、返回同一条缓存。
请修复 build_key：无参数时仍然只返回 URL；有参数时把参数按名字排序
拼进键里（形如 url?a=1&b=2）。get/put 的对外行为保持不变。
