"""简历渲染引擎入口

- 输入：ResumeData（dataclass）或 JSON dict
- 输出：PDF 文件路径
- 主题渲染实现按主题拆分在 renderers/ 包中
"""

from pathlib import Path

try:
    from .renderers import _RENDERERS
    from .models import ResumeData
    from .theme_manager import get_theme_manager
except ImportError:
    from renderers import _RENDERERS
    from models import ResumeData
    from theme_manager import get_theme_manager


def render_resume(
    resume_data: ResumeData | dict,
    output_path: str,
    theme: str = "professional",
) -> str:
    """渲染简历 PDF。"""
    if isinstance(resume_data, dict):
        resume_data = ResumeData.from_dict(resume_data)

    manager = get_theme_manager()
    css = manager.get_css(theme)

    if theme not in _RENDERERS:
        raise ValueError(f"不支持的主题: {theme}，可选: {list(_RENDERERS.keys())}")

    html_body = _RENDERERS[theme](resume_data)

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    from weasyprint import HTML
    HTML(string=full_html).write_pdf(output_path)
    return output_path


def render_resume_auto(
    resume_data: ResumeData | dict,
    output_path: str,
    theme: str = "professional",
) -> str:
    """自动选主题渲染（兼容接口统一）。"""
    return render_resume(resume_data, output_path, theme)
