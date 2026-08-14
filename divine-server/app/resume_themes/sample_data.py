"""
示例简历数据 — 用于生成 3 套主题示例 PDF
模拟一位 AI 产品经理的简历
"""

SAMPLE_RESUME = {
    "name": "张明",
    "title": "AI 产品经理 · 3 年经验 · 北京",
    "summary": (
        "3 年 AI 产品经验，主导 RAG 知识库与多模态内容生成平台从 0 到 1，"
        "擅长将大模型能力转化为可量化的用户价值。"
        "熟悉 LLM 应用架构、Agent 工作流与 RAG 评测体系。"
    ),
    "contact": {
        "email": "zhangming@email.com",
        "phone": "138-0000-0000",
        "website": "mingzhang.ai",
    },
    "experiences": [
        {
            "title": "高级产品经理",
            "company": "智谱科技",
            "period": "2024.03 - 至今",
            "description": "负责企业级知识库产品 GLM-KB 全生命周期管理",
            "highlights": [
                "从 0 到 1 设计 RAG pipeline，支持 50+ 文档格式解析与混合检索",
                "主导 Agent 工作流编辑器，拖拽式编排工具调用链，DAU 突破 5000+",
                "建立端到端评测体系，将回答准确率从 72% 提升至 89%",
            ],
        },
        {
            "title": "产品经理",
            "company": "字节跳动",
            "period": "2022.07 - 2024.02",
            "description": "负责剪映 AI 特效模块，探索 AIGC 在短视频创作中的落地",
            "highlights": [
                "设计「AI 绘画」功能（文生图 + 图生图），上线首月使用量破 200 万次",
                "推动「智能字幕」接入 Whisper 大模型，字幕生成效率提升 5 倍",
                "搭建 A/B 实验框架，优化特效推荐算法，CTR 提升 12%",
            ],
        },
    ],
    "education": [
        {
            "school": "清华大学",
            "degree": "硕士 · 人机交互",
            "period": "2019 - 2022",
            "description": "毕业论文《基于大语言模型的智能助手交互范式研究》",
        },
        {
            "school": "北京理工大学",
            "degree": "学士 · 计算机科学",
            "period": "2015 - 2019",
            "description": "GPA 3.8/4.0 · 优秀毕业生",
        },
    ],
    "projects": [
        {
            "name": "GLM-KB 企业知识库",
            "description": "面向 B 端的知识管理 SaaS，支持私有化部署与权限分级",
            "highlights": [
                "集成 50+ 文档格式解析，混合检索命中率 92%",
                "支持 SSO、审计日志、租户隔离，已签约 30+ 中大型企业",
            ],
        },
        {
            "name": "剪映 AI 绘画",
            "description": "短视频创作者的 AI 辅助绘画工具，内置 20+ 风格模板",
            "highlights": [
                "文生图 + 图生图双模式，支持局部重绘与风格迁移",
                "社区模板一键复用，UGC 模板月均新增 5000+",
            ],
        },
    ],
    "skills": [
        {"name": "产品规划", "level": 95},
        {"name": "LLM 应用架构", "level": 92},
        {"name": "Prompt 工程", "level": 90},
        {"name": "RAG 系统设计", "level": 88},
        {"name": "Agent 工作流", "level": 85},
        {"name": "用户研究", "level": 82},
        {"name": "数据分析", "level": 80},
        {"name": "Figma 原型", "level": 75},
        {"name": "A/B 测试", "level": 78},
    ],
    "skill_groups": {
        "产品核心": ["产品规划", "用户研究", "数据分析", "A/B 测试", "Figma 原型"],
        "AI 技术": ["LLM 应用架构", "Prompt 工程", "RAG 系统设计", "Agent 工作流"],
    },
}
