"""旧 8 主题桥接：纳入统一模板注册表，消除新旧两套体系的选型区分。

旧主题的渲染器（f-string 构建 + 内联 CSS）保持不变，此处只做接口适配：
包装成模板库模块形态（id / CSS / render），使 render_template_resume、
html_resume、行业推荐等统一入口对 20 套模板一视同仁。

注意：旧主题 CSS 自带 @page 等打印规则（非模块库的 PRINT_SINGLE 形态），
LEGACY 标记其 HTML 输出为单文件静态版（无编辑工具条）。
"""

from __future__ import annotations

from ..renderers import _RENDERERS
from ..themes import THEMES


class LegacyThemeModule:
    """把旧主题包装成模板库模块形态。"""

    LEGACY = True

    def __init__(self, theme_id: str, renderer_name: str):
        self.id = theme_id
        theme = THEMES[theme_id]
        self.display_name = theme["display_name"]
        # 旧主题 CSS 自带 @page/媒体规则，整段即最终 CSS
        self.CSS = theme["css"]
        self.PRINT_SINGLE = ""
        self._render = _RENDERERS[renderer_name]

    def render(self, resume) -> str:
        return self._render(resume)


# (注册表 id, 渲染器名) —— 旧主题 id 与渲染器一一对应
_LEGACY_THEMES = (
    ("professional", "professional"),
    ("creative", "creative"),
    ("minimal", "minimal"),
    ("boss_zhipin", "boss_zhipin"),
    ("finance", "finance"),
    ("linkedin", "linkedin"),
    ("kami", "kami"),
    ("kami_white", "kami_white"),
)


def register_all(register_module) -> None:
    for theme_id, renderer_name in _LEGACY_THEMES:
        register_module(LegacyThemeModule(theme_id, renderer_name))
