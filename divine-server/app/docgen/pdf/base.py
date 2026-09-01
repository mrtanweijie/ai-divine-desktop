from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 布局模块规范：追加到各 markdown 类 recipe 的内容生成 prompt，
# 让 Agent 知道可以用模块约定语法输出带设计感的正文。
MODULE_GUIDE = """
【可选·布局模块】你可以在正文中使用以下布局模块增强设计感
（不要堆砌，建议全篇 2-4 个，且尽量错开类型）：

1. 大数字指标（hero-stat）：表格 + 紧随其后的标记行 {: .hero-stat}，
   每行三列：指标 | 数值 | 变化（变化带 +/- 号）
   | 指标 | 数值 | 变化 |
   | --- | --- | --- |
   | DAU | 2.4M | +34% |
   {: .hero-stat}
2. 金句（pull-quote）：以引用块开头
   > [!quote] 关键洞察
   > 金句正文
   > — 来源
3. 提示框（callout）：> [!note] / [!info] / [!warning] / [!success] / [!error] + 标题 + 正文
4. 左右对比（two-col-compare）：两列表格 + {: .compare}，左列现状、右列目标
5. 时间线（timeline）：表格（时间|事件|说明|高亮可选填 yes）+ {: .timeline}
6. 特性网格（feature-grid）：表格（图标|特性|描述）+ {: .features}
7. 进度条（metric-row）：表格（指标|当前/目标|百分比如 80%）+ {: .metrics}
8. 标签云（tag-cloud）：表格（标签|是否高亮 yes）+ {: .tags}
9. 总结框（conclusion-box）：
   > [!conclusion] 下一步
   > 总结文字
10. 人物卡（bio-card）：
   > [!bio] 姓名 | 头衔
   > 简介文字

规则：表格标记行 {: .xxx} 必须紧跟表格最后一行；引用块必须以 > [!类型] 开头；
模块内容里的竖线 | 只在表格中使用，正文中不要使用 |。

【封面元数据（可选）】如果文档有封面需要展示的信息（团队、周期、负责人、
版本、关键词等），在正文最前面输出一行 HTML 注释，系统会自动读取并填充封面：
<!-- cover-meta: {"团队": "后端组", "周期": "8.11 – 8.17", "下周重点": "消息推送重构"} -->
支持字段：doc_type（文档类型）、info/meta（键值对字典）、badge、author、date、
issue_no、cta_text、footer、highlight.value/label/stats（split 封面大数字）。
"""

# 设计规格提示：追加在意图规划 prompt 之后，让 LLM 在同一调用里给出设计决策，
# 替代纯关键词查表；字段经 design_rules 校验，非法值自动忽略。
DESIGN_SPEC_HINT = """
【设计决策（可选）】根据文档的主题、行业与受众，在 JSON 顶层输出一个 design 对象：
{"design": {
  "base_theme": "版式骨架，从 universal(商务通用)/notion(轻量笔记)/linear(紧凑研发)/apple(圆润舒适)/modern(现代科技)/academic(学术衬线)/minimal(极简黑白)/roadmap(知识图谱) 中选最贴合的",
  "primary_color": "主色，颜色中文名或十六进制（如 红色、藏青、#1F3A5F），需贴合内容气质",
  "cover_style": "left-aligned|centered|split|minimal|hero-graphic|terminal 之一",
  "cover": true 或 false,
  "toc": true 或 false
}}
仅在有把握时输出 design；不确定就整体省略，系统会按场景自动决策。
"""



@dataclass
class PDFIntent:
    title: str
    topic: str
    style: str
    color_scheme: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class PDFRecipe:
    name: str = "simple"
    display_name: str = "文档"
    content_format: str = "markdown"
    css_template: str = "universal"
    color_scheme: str = "blue"
    # 内容生成是否支持大纲→分章两段式（结构强耦合的配方关闭，如 resume）
    sectioned_content: bool = True
    illustration_plan: dict[str, bool] = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint: str = (
        '{"title": "标题", "topic": "主题", '
        '"sections": [{"title": "章节标题", "key_points": ["要点"]}]}'
    )

    def build_intent_prompt(self, user_input: str) -> str:
        return (
            f"你是{self.display_name}规划器。根据用户需求输出 JSON，不要输出 JSON 以外的内容。\n"
            f"输出结构：{self.intent_json_hint}\n"
            + DESIGN_SPEC_HINT
            + f"\n用户输入：{user_input}"
        )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            f"你是资深{self.display_name}作者。根据文档结构撰写完整 Markdown 正文。\n"
            "要求：每个章节用 ## 标题；内容详实；"
            "不要自动生成 SVG 插图；仅当确实需要简单图标时才使用小型 SVG 图标。"
            f"主题：{intent.topic}"
        )

    def content_user_prompt(self, intent: PDFIntent) -> str:
        import json

        return json.dumps(
            {
                "title": intent.title,
                "sections": intent.sections,
                "meta": intent.meta,
            },
            ensure_ascii=False,
            indent=2,
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "文档"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {
                    "title": f"第 {index} 部分",
                    "key_points": [
                        f"围绕“{title}”展开第 {index} 部分的内容"
                    ],
                }
                for index in range(1, 4)
            ],
            meta={"recipe": self.name},
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        lines = [f"# {intent.title}", "", f"{intent.topic}", ""]
        for section in intent.sections:
            lines.append(f"## {section.get('title') or '章节'}")
            lines.append("")
            for point in section.get("key_points") or []:
                lines.append(f"- {point}")
            lines.append("")
        return "\n".join(lines).strip()
