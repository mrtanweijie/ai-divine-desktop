"""
简历主题管理器
- 加载/注册/切换主题
- 动态替换 CSS 变量
- 缓存编译后的 CSS
"""

from typing import Optional


class ThemeManager:
    """管理多套简历主题"""

    def __init__(self, themes: dict):
        self._themes = themes
        self._cache: dict[str, str] = {}

    def list_themes(self) -> list[dict]:
        """返回所有主题元信息（不含 CSS 原文）"""
        return [
            {
                "name": t["name"],
                "display_name": t["display_name"],
                "description": t["description"],
                "preview_color": t.get("preview_color", "#333"),
                "preview_accent": t.get("preview_accent", "#666"),
            }
            for t in self._themes.values()
        ]

    def get_css(self, theme_name: str) -> str:
        """获取指定主题的完整 CSS（带缓存）"""
        if theme_name not in self._themes:
            raise ValueError(f"未知主题: {theme_name}，可选: {list(self._themes.keys())}")

        if theme_name in self._cache:
            return self._cache[theme_name]

        css = self._themes[theme_name]["css"]
        self._cache[theme_name] = css
        return css

    def get_preview_html(self, theme_name: str) -> str:
        """生成主题预览缩略图 HTML"""
        info = self._themes[theme_name]
        color = info.get("preview_color", "#333")
        accent = info.get("preview_accent", "#666")
        return f"""
        <div style="background:white;border-radius:6px;overflow:hidden;border:1px solid #e0e0e0;width:100%;height:100%;display:flex;flex-direction:column;">
          <div style="height:38%;background:{color};padding:10px;display:flex;flex-direction:column;justify-content:center;">
            <div style="color:white;font-size:14px;font-weight:700;margin-bottom:3px;">张明远</div>
            <div style="color:rgba(255,255,255,0.7);font-size:8px;">高级产品经理</div>
          </div>
          <div style="flex:1;padding:8px 10px;display:flex;gap:8px;">
            <div style="width:35%;display:flex;flex-direction:column;gap:5px;">
              <div style="width:80%;height:4px;background:{accent};border-radius:2px;"></div>
              <div style="width:60%;height:3px;background:#e0e0e0;border-radius:2px;"></div>
              <div style="width:70%;height:3px;background:#e0e0e0;border-radius:2px;"></div>
              <div style="width:50%;height:3px;background:#e0e0e0;border-radius:2px;"></div>
            </div>
            <div style="flex:1;display:flex;flex-direction:column;gap:4px;">
              <div style="width:100%;height:5px;background:#f0f0f0;border-radius:2px;"></div>
              <div style="width:90%;height:3px;background:#e8e8e8;border-radius:2px;"></div>
              <div style="width:95%;height:3px;background:#e8e8e8;border-radius:2px;"></div>
              <div style="width:70%;height:3px;background:#e8e8e8;border-radius:2px;"></div>
            </div>
          </div>
        </div>
        """

    def register(self, name: str, display_name: str, description: str,
                 css: str, preview_color: str = "#333",
                 preview_accent: str = "#666"):
        """动态注册新主题"""
        self._themes[name] = {
            "name": name,
            "display_name": display_name,
            "description": description,
            "css": css,
            "preview_color": preview_color,
            "preview_accent": preview_accent,
        }
        self._cache.pop(name, None)


# 单例
_manager: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    global _manager
    if _manager is None:
        try:
            from .themes import THEMES
        except ImportError:
            from themes import THEMES
        _manager = ThemeManager(THEMES)
    return _manager
