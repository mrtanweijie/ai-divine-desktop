"""`/技能` 引用的解析与强注入（P1b · B5–B6）。

技能与文件语义不同：文件是**指代**（读什么由 agent 决定），技能是**指令**
（本轮必须按它执行）。所以技能不能沿用文件那套"只注入元数据"的策略：

- **knowledge 技能**：把 SKILL.md 正文（+ references）直接注入本轮消息前缀，
  不去赌 agent 会主动 `load_skill`（只给一行描述等于重复 prompt 里已有的技能
  目录，用户会认为"`/` 了没用"）；
- **executable 技能**：注入"必须调用工具 `skill_xxx`"+ 参数契约
  （`script_mode=json` → stdin JSON 参数；`cli` → 命令行 args）。

预算与上限（方案 025 §3.2 / §3.5）：

- 单技能正文 ≤ `MAX_SKILL_BODY_CHARS`，多技能累加 ≤ `MAX_SKILL_TOTAL_CHARS`，
  超限降级为"硬指令 + 描述"并在日志中标注；
- 单消息技能引用 ≤ `MAX_MENTION_SKILLS`，超出的忽略并提示。

技能集合来自 `skill_registry.scan(project_root=workspace)`——与 agent 侧
`refresh(ctx.workspace)` 同源、同 workspace，且**不写单例状态**，避免
"前端能选、后端用不了"（方案 §3.1 ①）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..agent.core import _skill_tool_name
from ..skills import skill_registry

logger = logging.getLogger(__name__)

# 一条消息最多生效的技能数（与前端弹层提示一致，见方案 §3.5）
MAX_MENTION_SKILLS = 3
# 单技能注入正文上限（字符）与多技能累加上限（方案 §3.2 预算）
MAX_SKILL_BODY_CHARS = 20_000
MAX_SKILL_TOTAL_CHARS = 40_000
# 保留字消歧前缀：技能名与斜杠指令同名时前端插入 `skill:名称`
SKILL_PREFIX = "skill:"


@dataclass
class InjectedSkill:
    """一个被成功解析并注入本轮上下文的技能。"""

    name: str
    type: str
    source: str
    description: str = ""
    tool_name: str | None = None
    inlined: bool = True


@dataclass
class SkillInjection:
    """技能引用的解析结果（供 chat 注入与"是否真的用了"校验复用）。"""

    block: str = ""
    skills: list[InjectedSkill] = field(default_factory=list)
    # 技能不存在 / 已卸载 / 不在当前会话工作区可见范围内 → 剔除
    invalid: list[str] = field(default_factory=list)
    # 正文超预算 → 降级为硬指令（load_skill）
    degraded: list[str] = field(default_factory=list)
    # 超出单消息技能数上限 → 直接忽略
    dropped: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        """本轮生效的技能名（顺序 = 用户选择顺序）。"""
        return [skill.name for skill in self.skills]


def normalize_skill_name(raw: str) -> str:
    """剥掉 `skill:` 消歧前缀（该前缀只用于输入框消歧，不是技能名）。"""
    name = (raw or "").strip()
    while name[: len(SKILL_PREFIX)].lower() == SKILL_PREFIX:
        name = name[len(SKILL_PREFIX) :].strip()
    return name


def _usage_hint(skill) -> str:
    """能力技能的执行方式：stdin JSON 参数 或 命令行参数。"""
    if skill.script_mode == "json":
        return "参数通过 stdin JSON（params）传入"
    return "参数以命令行参数（args）传入"


def _knowledge_section(skill, body: str, references: str) -> str:
    lines = [
        f"- {skill.name}（知识技能，来源：{skill.source}）："
        "本轮必须严格按下述技能正文执行；正文已完整注入，"
        "不要再调用 load_skill 重复加载，也不要只复述它的步骤。",
        "```text",
        body,
        "```",
    ]
    if references:
        lines.append("参考资料：")
        lines.append("```text")
        lines.append(references)
        lines.append("```")
    return "\n".join(lines)


def _degraded_section(skill) -> str:
    """超预算降级：只给硬指令 + 描述，由 agent 自行 load_skill 取正文。"""
    hint = f"：{skill.description}" if skill.description else ""
    return (
        f"- {skill.name}（知识技能，来源：{skill.source}{hint}）："
        f'本轮必须首先调用 load_skill("{skill.name}") 加载完整正文并严格执行'
        "（正文超出注入预算，未内联）。"
    )


def _executable_section(skill, tool_name: str) -> str:
    return (
        f"- {skill.name}（能力技能，来源：{skill.source}）："
        f"本轮必须真正调用工具 {tool_name} 执行（{_usage_hint(skill)}）；"
        "不要只描述步骤，也不要把脚本内容抄进回答。"
    )


def resolve_skill_mentions(
    names: Iterable[str],
    workspace: Path | None,
) -> SkillInjection:
    """把消息里的 `/技能` 引用解析成注入段落 + 生效技能清单。

    - 按用户选择顺序去重、逐个在当前会话工作区可见的技能集合里查找；
    - 找不到的技能记入 `invalid`（前端可据此提示"技能已被卸载"）；
    - 超出 `MAX_MENTION_SKILLS` 的记入 `dropped`；
    - 正文超出预算的记入 `degraded`，降级为 load_skill 硬指令。
    """
    wanted: list[str] = []
    for raw in names or ():
        name = normalize_skill_name(str(raw))
        if name and name not in wanted:
            wanted.append(name)
    result = SkillInjection()
    if not wanted:
        return result

    try:
        metas = skill_registry.scan(project_root=workspace)
    except Exception:  # noqa: BLE001 — 技能扫描失败不应阻断对话
        logger.exception("技能引用解析：扫描技能失败（workspace=%s）", workspace)
        metas = {}

    sections: list[str] = []
    remaining = MAX_SKILL_TOTAL_CHARS
    for name in wanted:
        if len(result.skills) >= MAX_MENTION_SKILLS:
            result.dropped.append(name)
            continue
        meta = metas.get(name)
        if meta is None:
            result.invalid.append(name)
            continue

        if meta.type == "executable" and meta.script_path is not None:
            tool_name = _skill_tool_name(meta.name)
            result.skills.append(
                InjectedSkill(
                    name=meta.name,
                    type=meta.type,
                    source=meta.source,
                    description=meta.description,
                    tool_name=tool_name,
                )
            )
            sections.append(_executable_section(meta, tool_name))
            continue

        body = (meta.body or "").strip()
        references = (meta.references_content or "").strip()
        payload_len = len(body) + len(references)
        over_budget = (
            len(body) > MAX_SKILL_BODY_CHARS
            or payload_len > remaining
            or payload_len > MAX_SKILL_TOTAL_CHARS
        )
        if over_budget or not body:
            result.degraded.append(name)
            result.skills.append(
                InjectedSkill(
                    name=meta.name,
                    type=meta.type,
                    source=meta.source,
                    description=meta.description,
                    inlined=False,
                )
            )
            sections.append(_degraded_section(meta))
            logger.info(
                "技能正文超预算，降级为硬指令：skill=%s body_len=%d refs_len=%d",
                name,
                len(body),
                len(references),
            )
            continue

        if len(body) > MAX_SKILL_BODY_CHARS:
            body = body[:MAX_SKILL_BODY_CHARS]
        remaining -= payload_len
        result.skills.append(
            InjectedSkill(
                name=meta.name,
                type=meta.type,
                source=meta.source,
                description=meta.description,
            )
        )
        sections.append(_knowledge_section(meta, body, references))

    if result.invalid:
        logger.warning(
            "剔除 %d 个失效的 / 技能引用（不存在或不可见）：%s",
            len(result.invalid),
            result.invalid,
        )
    if result.dropped:
        logger.info(
            "忽略超出上限（%d）的技能引用：%s", MAX_MENTION_SKILLS, result.dropped
        )

    lines = [
        "（用户通过 / 显式指定了本轮必须使用的技能，"
        "它们优先于你的默认做法，请直接执行，不要反问是否使用："
    ]
    lines.extend(sections)
    if result.invalid:
        lines.append(
            "- 以下技能不存在或已卸载，已忽略："
            + "、".join(result.invalid)
            + "（若用户确实需要，请说明并给出替代方案）"
        )
    if result.dropped:
        lines.append(
            f"- 其余 {len(result.dropped)} 个技能引用已忽略"
            f"（单条消息最多 {MAX_MENTION_SKILLS} 个）："
            + "、".join(result.dropped)
        )
    lines.append("）")
    result.block = "\n".join(lines)
    return result
