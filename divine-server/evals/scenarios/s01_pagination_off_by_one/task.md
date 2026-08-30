pager.py 里的分页函数有 bug：page=1 应该返回第一页（前 per_page 条数据），
但现在返回的是第二页。请修复 paginate，保持 page_count 和参数校验的行为不变。
