"""多页布局的通用打印 CSS（与外部模板 multipage 版的第二个 @media print 块一致）。

单页模式的打印 CSS 由各模板模块自带（@page margin:0 + 模板各自的 .page/色块规则）；
多页模式在其后追加本块：浏览器/WeasyPrint 按 CSS 级联以后者覆盖 @page 与 .page，
并加入断页保护（条目不跨页、章节标题不孤悬页尾、ul/ol 孤行控制）。
"""

from __future__ import annotations

MULTI_PRINT_CSS = """
@media print{
  @page{size:A4;margin:10mm 0 11mm}
  .page{min-height:0;margin:0;box-shadow:none}
  .item,.work,.proj,.block,.tcard,.kv,.line,.pubs li,.g,tr,.foot{break-inside:avoid}
  h2{break-after:avoid}
  ul,ol{orphans:2;widows:2}
}
"""

# 双栏紧凑版多页打印时侧栏转顶部通栏，避免第二页大面积空白（与源模板 mp-extra 一致）
COMPACT_MULTI_EXTRA_CSS = """
@media print{.page{display:block}.side{width:auto}}
"""


def assemble_css(module, layout: str) -> str:
    """module 需提供 CSS 与 PRINT_SINGLE 属性；multi 追加通用多页块。"""
    css = module.CSS + "\n" + module.PRINT_SINGLE
    if layout == "multi":
        css += "\n" + MULTI_PRINT_CSS
        if getattr(module, "MULTI_EXTRA", ""):
            css += "\n" + module.MULTI_EXTRA
    return css
