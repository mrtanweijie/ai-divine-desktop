from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..docgen.pdf.theme_manager import (
    build_cover_html,
    build_html_template_document,
    html_template_pages,
    list_available_themes,
    load_theme_css,
    theme_owns_cover,
)

router = APIRouter(prefix="/pdf", tags=["pdf"])


class PreviewCssRequest(BaseModel):
    theme_id: str = "modern"
    overrides: dict[str, str] = {}
    paper_size: str = "A4"


class RenderPreviewRequest(BaseModel):
    theme_id: str = "modern"
    sample_content: str = ""


@router.get("/themes")
def list_themes():
    return {"themes": list_available_themes()}


@router.post("/preview-css")
def preview_css(req: PreviewCssRequest):
    try:
        return {
            "css": load_theme_css(
                req.theme_id,
                req.overrides or None,
                req.paper_size,
            ),
            "theme": req.theme_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/render-preview")
def render_preview(req: RenderPreviewRequest):
    try:
        # 页式模板（论文/报告四套）自带封面与固定页结构，
        # markdown + 通用封面拼出来会散架；直接渲染模板自身的页片段。
        if theme_owns_cover(req.theme_id):
            pages = "\n".join(html_template_pages(req.theme_id))
            if pages:
                return {
                    "html": build_html_template_document(
                        pages, "主题效果预览", theme=req.theme_id
                    ),
                    "theme": req.theme_id,
                }
        css = load_theme_css(req.theme_id)
        content = req.sample_content.strip() or _default_sample()
        import markdown as markdown_lib

        body = markdown_lib.markdown(
            content,
            extensions=["extra", "tables", "fenced_code", "sane_lists"],
        )
        cover = build_cover_html(req.theme_id, "主题效果预览", req.theme_id)
        html = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<style>{css}</style></head><body>"
            f"{cover}{body}</body></html>"
        )
        return {"html": html, "theme": req.theme_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _default_sample() -> str:
    return """## 这是二级标题

这是一段正文示例，展示字体、行高、颜色效果。

### 三级标题

- 列表项一
- 列表项二
- **加粗文本** 和 *斜体文本*

> 这是一段引用文字，展示引用块样式。

```python
def hello():
    print("Hello, PDF!")
```

| 项目 | 状态 |
| --- | --- |
| 功能 A | 完成 |
| 功能 B | 进行中 |
"""
