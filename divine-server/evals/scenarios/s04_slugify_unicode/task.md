slugs.py 的 slugify 没有做 Unicode 折叠："Café Über" 应该得到 "cafe-uber"，
"  Résumé  " 应该得到 "resume"，但目前带音调的字母会破坏结果。
请按 docstring 里的规范修复（先折叠音调再做替换），其余行为保持不变。
