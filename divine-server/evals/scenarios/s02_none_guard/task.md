durations.py 的 parse_duration 有输入校验问题：项目规范要求输入为 None 或空字符串时
抛 ValueError（错误信息任意），但现在传 None 会抛 AttributeError。
请修复，同时保证合法输入（2h/12m/45s）和非法文本（如 "soon"）的行为不变。
