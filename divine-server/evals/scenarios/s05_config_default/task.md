service.py 的 call_remote 在不传 timeout 时应该使用 config.py 里定义的
DEFAULT_TIMEOUT（当前是 30），但现在实际用的是写死的另一个值。
请修复，让默认超时统一从 config 读取；显式传入 timeout 的行为保持不变。
