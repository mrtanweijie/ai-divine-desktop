"""简历模板库（12 套设计母版）渲染入口。

- 输入：ResumeData（dataclass）或 JSON dict
- 输出：PDF / 可编辑 HTML / 纯净 HTML（按 output_format）
- HTML 与外部母版体验一致：浏览器打开即可点击编辑，⌘P 导出 PDF；
  纯净版无工具条与编辑属性，可直接投递。
- 每套模板 = 一个 tXX 模块（CSS 原文 + render 函数），见 registry.py。
"""

from __future__ import annotations

from pathlib import Path

try:
    from . import registry
    from .components import page_foot, toolbar_html, wrap_page
    from .print_css import assemble_css
except ImportError:  # 兼容脚本直接运行
    import registry  # type: ignore
    from components import page_foot, toolbar_html, wrap_page  # type: ignore
    from print_css import assemble_css  # type: ignore

try:
    from ..models import ResumeData
except ImportError:
    from models import ResumeData  # type: ignore

# 模板 id -> 渲染模块（懒加载注册，由各 tXX 模块在底部调用 register）
_MODULES: dict[str, object] = {}


def register_module(module) -> None:
    """tXX 模块自注册：要求提供 id / CSS / PRINT_SINGLE / render。"""
    _MODULES[module.id] = module


def _load_module(template_id: str):
    if template_id in _MODULES:
        return _MODULES[template_id]
    entry = registry.get_entry(template_id)
    module = __import__(f"{__name__}.{entry['module']}", fromlist=["render"])
    register_module(module)
    return module


def _ensure_resume(resume_data) -> ResumeData:
    if isinstance(resume_data, ResumeData):
        return resume_data
    return ResumeData.from_dict(resume_data)


def build_html(resume_data, template_id: str, layout: str = "single",
               *, editable: bool) -> str:
    """渲染完整 HTML 文档字符串（editable=False 为纯净版）。"""
    resume = _ensure_resume(resume_data)
    entry = registry.get_entry(template_id)
    module = _load_module(template_id)
    css = assemble_css(module, layout)
    body = module.render(resume)
    title = f"{resume.name or '简历'}-{entry['display_name']}"
    toolbar = toolbar_html(entry["display_name"], entry["tip"]) if editable else ""
    return wrap_page(body, title=title, css=css, editable=editable, toolbar=toolbar)


def render_template_resume(
    resume_data,
    output_path: str,
    template_id: str,
    layout: str = "single",
    output_format: str = "pdf",
) -> list[str]:
    """按模板渲染简历，返回生成的文件路径列表。

    - output_format="pdf"：仅 PDF（WeasyPrint，print media 自动隐藏工具条）
    - output_format="html"：可编辑 HTML + 纯净 HTML（与 PDF 同目录，同名 .html/.html_clean）
    - output_format="both"：PDF + 两个 HTML
    """
    entry = registry.get_entry(template_id)
    if layout not in ("single", "multi"):
        layout = "single"
    output_format = output_format if output_format in ("pdf", "html", "both") else "pdf"

    resume = _ensure_resume(resume_data)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    generated: list[str] = []

    if output_format in ("html", "both"):
        html_path = output.with_suffix(".html")
        html_path.write_text(
            build_html(resume, template_id, layout, editable=True), encoding="utf-8"
        )
        generated.append(str(html_path))
        clean_path = output.with_suffix(".html_clean.html")
        clean_path.write_text(
            build_html(resume, template_id, layout, editable=False), encoding="utf-8"
        )
        generated.append(str(clean_path))

    if output_format in ("pdf", "both"):
        full_html = build_html(resume, template_id, layout, editable=True)
        from weasyprint import HTML

        HTML(string=full_html).write_pdf(str(output))
        generated.insert(0, str(output))

    return generated


__all__ = [
    "TEMPLATE_IDS",
    "build_html",
    "register_module",
    "render_template_resume",
    "page_foot",
    "toolbar_html",
]
