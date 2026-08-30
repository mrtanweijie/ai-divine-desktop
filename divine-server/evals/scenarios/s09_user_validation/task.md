给 models.py 的 User 增加邮箱校验，规则如下：
- 校验逻辑放在静态方法 is_valid_email(email) -> bool 里；
- 合法要求：恰好一个 @；@ 前后都非空且不含空格；
  域名部分必须包含至少一个点，且点不能在域名开头或结尾；
- __init__ 里 email 不合法时抛 ValueError（错误信息以 invalid email 开头即可）；
- 合法邮箱的创建行为保持不变。
