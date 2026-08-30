pipeline.py 的 clean_line 按规范应该去掉首尾所有空白（包括制表符），
但目前 \thello\t 清洗后还是 "\thello\t"。
normalize.strip_spaces 是旧接口、只能去空格，pipeline 不应依赖它做这一步。
请修复 clean_line（不要改 normalize.py 的对外行为），其他清洗行为保持不变。
