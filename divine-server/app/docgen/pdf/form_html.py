"""基于 HTML 模板库（docs/pdf-forms）的可填写表单 PDF 渲染管线。

三阶段（docs/design/018-pdf-form-html-templates-20260906.md）：
1. HTML 组装：内置模板实例化 或 模型拼装的组合 HTML；
   将每个 [data-field] 的视觉控件替换为携带 pdf-form:// 链接的定位锚点；
2. WeasyPrint 渲染：协议标记 + forms.css 出 PDF（链接注解 = 槽位精确 rect）；
3. pymupdf 控件放置：按链接注解放置 AcroForm 真控件（透明填充，
   CSS 画的下划线/盒子透出；勾选类控件白底自绘，覆盖静态样式）。

字段协议（模板库约定）：data-field/data-type/data-label/data-required/data-checked。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import pymupdf
from bs4 import BeautifulSoup

_FILL_SCHEME = "pdf-form://"
# 这些 data-type 只做视觉呈现，不放控件（打印后手填/手签）
_VISUAL_ONLY_TYPES = {"signature", "rating", "nps"}
# 期二递归处理的容器类型
_CONTAINER_TYPES = {"table", "group"}
_OPTIONS_IN_QUERY = {"select"}

_FILL_BOX_CSS = (
    "\n/* pdf_form_generate 控件锚点：链接注解载体（打印不可见，仅提供 rect） */\n"
    "a.fill-anchor{display:inline-block;text-decoration:none;color:inherit}\n"
)


def form_templates_dir() -> Path:
    """定位模板库目录：冻结包资源 → 仓库 docs/pdf-forms。"""
    meipass = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else None
    if meipass and (meipass / "pdf-forms").is_dir():
        return meipass / "pdf-forms"
    repo_docs = Path(__file__).resolve().parents[4] / "docs" / "pdf-forms"
    if repo_docs.is_dir():
        return repo_docs
    raise FileNotFoundError("PDF 表单模板库目录未找到（docs/pdf-forms）")


def list_templates() -> list[dict[str, str]]:
    """枚举内置模板（01-application 等）。"""
    d = form_templates_dir()
    templates = []
    for path in sorted(d.glob("*.html")):
        m = re.match(r"^(\d+)-([a-z-]+)\.html$", path.name)
        if not m or path.name == "00-index.html":
            continue
        templates.append({"id": m.group(2), "file": path.name, "no": int(m.group(1))})
    return templates


def set_theme(html: str, theme: str) -> str:
    """切换 <html data-theme>（minimal/corporate/tech/forest）。"""
    if not theme:
        return html
    soup = BeautifulSoup(html, "html.parser")
    html_el = soup.find("html")
    if html_el is None:
        return html
    html_el["data-theme"] = theme
    return str(soup)


def load_template(template_id: str) -> str:
    for entry in list_templates():
        if entry["id"] == template_id:
            return (form_templates_dir() / entry["file"]).read_text(encoding="utf-8")
    raise ValueError(f"未知模板: {template_id!r}")


# 12 列栅格的像素几何（forms.css：内容宽约 400px + gap 10px；A4 内容宽约 510px）
_GRID_CONTENT_PX = 400.0
_GRID_GAP_PX = 10.0


def _grid_span_px(span: int) -> float:
    """col-N 栅格类对应的实际像素宽度（含跨列的 gap）。"""
    col_w = (_GRID_CONTENT_PX - 11 * _GRID_GAP_PX) / 12
    return span * col_w + (span - 1) * _GRID_GAP_PX


def _fill_anchor(href: str, classes: str | None, extra_attrs: dict[str, str] | None = None):
    a = BeautifulSoup("", "html.parser").new_tag("a")
    a["href"] = href
    a["class"] = (classes.split() if classes else []) + ["fill-anchor"]
    for k, v in (extra_attrs or {}).items():
        a[k] = v
    return a


def prepare_html(
    html: str,
    values: dict[str, Any] | None = None,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """把协议标记的 HTML 准备为可渲染形态；返回 (prepared_html, 字段元表)。

    - 每个视觉控件替换为 pdf-form:// 定位锚点（保留原 class 供 CSS 继承）；
    - radio/勾选组：每个 .opt-box → name::选项 引用；
    - values：字段预填值（控件创建时作为默认值）；
    - signature/rating/nps：视觉占位不放控件；
    - table/group：期二递归（当前原样保留、记 warning）。
    """
    values = {str(k): str(v) for k, v in (values or {}).items()}
    soup = BeautifulSoup(html, "html.parser")
    meta_by_ref: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for field_el in soup.select("[data-field]"):
        fname = (field_el.get("data-field") or "").strip()
        ftype = (field_el.get("data-type") or "text").strip().lower()
        label = field_el.get("data-label") or ""
        required = field_el.get("data-required") == "true"
        if not fname:
            continue
        if ftype in _VISUAL_ONLY_TYPES:
            continue
        if ftype in _CONTAINER_TYPES:
            # 子表/分组容器：容器本身跳过；嵌套的 [data-field] 由通用循环处理；
            # 无 data-field 的裸控件按 "表名.列头#行号" 派生子字段（包裹式锚点，
            # 保留原控件元素——.cell 内的输入样式依赖元素上下文，不能替换）。
            print(f"DBG container: {fname}", file=sys.stderr)
            headers = [th.get_text(strip=True) for th in field_el.select("thead th")]
            for r_index, row in enumerate(field_el.select("tbody tr"), 1):
                cells = row.select("td")
                for c_index, cell in enumerate(cells, 1):
                    sub_ctrl = cell.select_one("input, textarea, select")
                    if sub_ctrl is None or sub_ctrl.get("data-field"):
                        continue
                    # 嵌套在更深 [data-field] 内的控件（如三段式日期）由该字段整体处理
                    deeper = sub_ctrl.find_parent(attrs={"data-field": True})
                    if deeper is not None and deeper is not field_el:
                        continue
                    # 列名：thead 列头优先；无 thead 的标签-值网格用前置单元格文本
                    col_name = ""
                    if c_index - 2 >= 0:
                        prev_text = re.sub(r"[\s*i]+$", "", cells[c_index - 2].get_text(strip=True))
                        col_name = prev_text.strip()
                    if not col_name and c_index - 1 < len(headers) and headers[c_index - 1]:
                        col_name = headers[c_index - 1]
                    if not col_name:
                        continue
                    sub_name = f"{fname}.{col_name}#{r_index}"
                    sub_type = {"textarea": "textarea", "select": "select"}.get(sub_ctrl.name, "text")
                    href = _FILL_SCHEME + quote(sub_name, safe="")
                    placeholder = sub_ctrl.get("placeholder") or ""
                    anchor = _fill_anchor(href, "ctrl ctrl--underline fill-anchor")
                    anchor.string = placeholder or "\u00a0"
                    meta_by_ref[sub_name] = {
                        "field": sub_name, "type": sub_type, "label": col_name,
                        "required": False, "options": [],
                        "default": sub_ctrl.get("placeholder") or "",
                    }
            continue

        if ftype == "radio" or (ftype == "checkbox" and field_el.select_one(".opt-group")):
            # 选项组：每个 .opt-box → name::选项 锚点
            # values 显式指定时优先于模板 data-checked（避免双勾选）
            for box in field_el.select(".opt-box"):
                label_el = box.find_parent("label")
                option = (label_el.get_text(strip=True) if label_el else "") or f"选项{len(meta_by_ref)+1}"
                ref = f"{fname}::{option}"
                href = _FILL_SCHEME + quote(ref, safe="")
                if fname in values:
                    checked = (values[fname] == option)
                else:
                    checked = (box.get("data-checked") == "true")
                anchor = _fill_anchor(href, " ".join(box.get("class", [])), {"data-checked": "true" if checked else None})
                box.replace_with(anchor)
                meta_by_ref[ref] = {
                    "field": fname, "option": option, "type": "checkbox",
                    "label": label, "required": required,
                    "default": option if checked else None,
                }
            continue

        ctrl = field_el.select_one("input, textarea, select")
        date_triple = field_el.select_one(".date-triple") or (
            field_el if "date-triple" in (field_el.get("class") or []) else None
        )
        if ftype == "date" and date_triple is not None:
            # 三段式日期（年/月/日）：整容器替换为单锚点，避免残留静态输入框
            ref = fname
            href = _FILL_SCHEME + quote(ref, safe="")
            anchor = _fill_anchor(href, "ctrl ctrl--underline fill-anchor")
            date_triple.replace_with(anchor)
            meta_by_ref[ref] = {
                "field": fname, "type": "text", "label": label, "required": required,
                "options": [], "default": "",
            }
            continue
        if ctrl is None:
            ctrl = field_el.select_one("a")  # 模板可能已含锚点（幂等）
        if ctrl is None:
            warnings.append(f"字段 {fname} 未找到控件元素，已跳过")
            continue

        ref = fname
        opts: list[str] = []
        if ftype == "select" or ctrl.name == "select":
            opts = [o.get_text(strip=True) for o in ctrl.select("option") if o.get_text(strip=True)]
        ctrl_class = " ".join(ctrl.get("class", []))
        default = ""
        placeholder = ""
        if ctrl.get("placeholder"):
            placeholder = str(ctrl.get("placeholder")).strip()
        elif ctrl.name == "textarea":
            placeholder = ctrl.get_text(strip=True)[:30]
        # 锚点内容：值或占位提示（内容驱动盒尺寸；WeasyPrint 的 grid 内
        # 空元素宽高计算不可靠，内容驱动的文本盒尺寸最稳）
        if ctrl.name == "textarea":
            default = ctrl.get_text(strip=True)
        elif ctrl.get("value") is not None:
            default = str(ctrl.get("value"))
        expected = values.get(fname, default)

        href = _FILL_SCHEME + quote(ref, safe="")
        if opts:
            href += "?opts=" + quote(",".join(opts), safe="")
        anchor = _fill_anchor(href, ctrl_class or "ctrl")
        # 显式内联宽高：WeasyPrint 66 在 grid item 内对空元素的
        # width:100%/min-height 解析有缺陷，必须用绝对像素
        anchor["data-value"] = expected
        ctrl.replace_with(anchor)
        meta_by_ref[ref] = {
            "field": fname, "type": ftype, "label": label, "required": required,
            "options": opts, "default": expected,
        }

    return str(soup), meta_by_ref


_ANCHOR_CSS = (
    "\n<style>/* pdf_form_generate 控件锚点：链接注解载体（透明，仅提供 rect） */\n"
    "a.fill-anchor{display:inline-block;box-sizing:border-box;text-decoration:none;"
    "color:inherit;font-family:inherit}\n</style>\n"
)


def theme_override_css(
    color_scheme: str | None, theme_colors: dict[str, str] | None
) -> str:
    """自定义主题色 → forms.css token 覆盖块（复用 colorize 的色词解析与 HSL 派生）。

    theme_colors 的 --color-primary/--color-accent（prompt 约定形态）与
    color_scheme（色名/#hex）都支持；无色彩系（黑/灰）派生为灰阶。
    """
    from app.docgen.resume.templates.colorize import (
        _rgb_to_hex,
        derive_resume_palette,
        resolve_color,
    )

    primary = None
    accent = None
    if theme_colors:
        primary = theme_colors.get("--color-primary")
        accent = theme_colors.get("--color-accent")
    if color_scheme and not primary:
        primary = color_scheme
    if not primary:
        return ""
    rgb = resolve_color(primary)
    if not rgb:
        return ""
    palette = derive_resume_palette(rgb)
    if accent:
        accent_rgb = resolve_color(accent)
        if accent_rgb:
            palette["accent"] = _rgb_to_hex(accent_rgb)
    block = (
        f":root{{--primary:{palette['main']};--primary-light:{palette['soft']};"
        f"--accent:{palette['accent']};}}"
    )
    return f"<style>{block}</style>\n"


def render_pdf(
    prepared_html: str, templates_dir: Path, extra_css: str = ""
) -> bytes:
    """WeasyPrint 渲染（base_url 指向模板库以解析 forms.css/图片）。"""
    from weasyprint import HTML

    # 注入锚点显示规则：.ctrl 只有 width:100% 没有 display，
    # 锚点（a 元素）不设 display 会塌缩成几 pt 宽
    head_css = _ANCHOR_CSS + extra_css
    if "</head>" in prepared_html:
        prepared_html = prepared_html.replace("</head>", f"<style>{head_css}</style></head>", 1)
    else:
        prepared_html = f"<style>{head_css}</style>" + prepared_html
    return HTML(
        string=prepared_html, base_url=str(templates_dir) + "/"
    ).write_pdf()


def place_widgets(pdf_bytes: bytes, meta_by_ref: dict[str, dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """扫描 pdf-form:// 链接注解，按字段类型放置 AcroForm 控件。"""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    filled_counter: dict[str, int] = {}
    warnings: list[str] = []

    for page in doc:
        for link in page.get_links():
            uri = link.get("uri", "")
            if not uri.startswith(_FILL_SCHEME):
                continue
            ref = unquote(urlparse(uri).netloc + urlparse(uri).path)
            meta = meta_by_ref.get(ref)  # query 的 opts 已在 meta.options 中
            if meta is None:
                warnings.append(f"链接 {ref!r} 无字段元数据，已跳过")
                continue
            rect = pymupdf.Rect(link["from"])
            if rect.x1 - rect.x0 <= 0.5 or rect.y1 - rect.y0 <= 0.5:
                warnings.append(f"槽位 {ref!r} 的链接矩形退化，已跳过")
                continue
            widget = pymupdf.Widget()
            widget.rect = rect
            widget.field_name = meta["field"]
            if meta.get("label"):
                widget.field_label = meta["label"]  # tooltip = data-label（协议承诺）
            widget.text_color = (0.12, 0.16, 0.2)
            widget.border_width = 0  # 视觉由 CSS 提供，控件透明
            widget.border_color = None
            widget.fill_color = None
            ftype = meta["type"]

            if meta.get("option") is not None:
                # 分组单选的子控件：白底自绘（覆盖模板静态勾选态）
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
                widget.field_name = ref  # name::选项 —— 填写互斥语义依赖完整名
                widget.fill_color = (1, 1, 1)
                widget.border_color = (0.42, 0.45, 0.5)
                widget.border_width = 1
                expected = meta.get("default", "")
                widget.field_value = bool(meta.get("option") == expected)
            elif ftype == "select":
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
                widget.choice_values = meta.get("options") or []
                widget.field_value = meta.get("default") if meta.get("default") in widget.choice_values else (widget.choice_values[0] if widget.choice_values else "")
            elif ftype == "textarea":
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.field_flags = 4096  # 多行
                widget.field_value = meta.get("default", "")
                widget.text_fontsize = 9
            else:  # text / number / money / date
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.field_value = meta.get("default", "")
                widget.text_fontsize = 10
            if meta.get("required"):
                widget.field_flags = (widget.field_flags or 0) | 2  # Required 位
            page.add_widget(widget)
            filled_counter[meta["field"]] = filled_counter.get(meta["field"], 0) + 1

    # CJK 值的控件外观由阅读器重绘（pymupdf 生成的 appearance 对中文有缺陷）
    try:
        doc.need_appearances(True)
    except Exception:  # noqa: BLE001
        pass
    report = {
        "filled": [{"key": k, "count": v} for k, v in sorted(filled_counter.items())],
        "missed": [],
        "warnings": warnings,
    }
    return doc, report


def verify_form(pdf_bytes: bytes, meta_by_ref: dict[str, dict[str, Any]]) -> list[str]:
    """改后自检：重开 PDF，断言每个 data-field 都有交互控件。"""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    actual: set[str] = set()
    for page in doc:
        for widget in page.widgets() or []:
            if widget.field_name:
                actual.add(widget.field_name.split("::")[0])
    doc.close()
    expected = {m["field"] for m in meta_by_ref.values()}
    missing = sorted(expected - actual)
    if missing:
        return [f"缺少交互控件的字段: {', '.join(missing)}"]
    return []
