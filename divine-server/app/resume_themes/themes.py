"""
简历主题注册表
- 各主题 CSS 定义拆在 theme_css/ 包中
- THEMES 是主题管理器的唯一注册入口
"""

from __future__ import annotations

from .kami_css import KAMI_CSS as KAMI_ORIGINAL_CSS
from .kami_css import KAMI_WHITE_CSS as KAMI_WHITE_ORIGINAL_CSS
from .theme_css import (
    BOSS_ZHIPIN_CSS,
    CREATIVE_CSS,
    FINANCE_CSS,
    LINKEDIN_CSS,
    MINIMAL_CSS,
    PROFESSIONAL_CSS,
)

THEMES = {
    "professional": {
        "name": "professional",
        "display_name": "经典商务蓝",
        "description": "左深蓝侧边栏 + 右白主内容区，适合投传统行业/大厂/外企",
        "css": PROFESSIONAL_CSS,
        "preview_color": "#1e3a5f",
        "preview_accent": "#93c5fd",
    },
    "creative": {
        "name": "creative",
        "display_name": "现代创意紫橙",
        "description": "顶部渐变 Header + 卡片式布局，适合设计/互联网/创业公司",
        "css": CREATIVE_CSS,
        "preview_color": "#7c3aed",
        "preview_accent": "#ec4899",
    },
    "minimal": {
        "name": "minimal",
        "display_name": "极简黑白",
        "description": "大量留白 + 细线分隔，适合学术/咨询/金融/法律",
        "css": MINIMAL_CSS,
        "preview_color": "#1a1a1a",
        "preview_accent": "#666666",
    },
    "boss_zhipin": {
        "name": "boss_zhipin",
        "display_name": "BOSS 直聘",
        "description": "单栏流式、ATS 友好、克制商务蓝，适合招聘平台投递",
        "css": BOSS_ZHIPIN_CSS,
        "preview_color": "#1a3d6e",
        "preview_accent": "#6b7280",
    },
    "finance": {
        "name": "finance",
        "display_name": "金融经典",
        "description": "衬线字体、黑白双线、克制正式，适合金融/银行/投行/证券",
        "css": FINANCE_CSS,
        "preview_color": "#1a1a1a",
        "preview_accent": "#444444",
    },
    "linkedin": {
        "name": "linkedin",
        "display_name": "LinkedIn 领英",
        "description": "品牌蓝条 + 蓝色强调 + 标签技能，适合 LinkedIn/海外/外企投递",
        "css": LINKEDIN_CSS,
        "preview_color": "#0a66c2",
        "preview_accent": "#e8f0fe",
    },
    "kami": {
        "name": "kami",
        "display_name": "Kami 暖色",
        "description": "Kami 原版暖色纸感底，4 数字卡片 + 3 步时间线 + 项目三段式，2 页",
        "css": KAMI_ORIGINAL_CSS,
        "preview_color": "#f5f4ed",
        "preview_accent": "#1B365D",
    },
    "kami_white": {
        "name": "kami_white",
        "display_name": "Kami 纯白",
        "description": "Kami 纯白投递版，打印零风险，同样保留数字卡片与项目三段式",
        "css": KAMI_WHITE_ORIGINAL_CSS,
        "preview_color": "#ffffff",
        "preview_accent": "#1B365D",
    },
}
