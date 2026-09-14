"""`/技能` 引用的解析与强注入（P1b · B5/B6/B13）测试。

覆盖：知识技能正文内联、能力技能工具契约注入、`skill:` 消歧前缀、失效技能剔除、
单消息技能数上限、超预算降级为硬指令，以及结束时的 “技能是否真的被使用” 校验。
"""

from __future__ import annotations

from pathlib import Path

from app.agent.core import _skill_tool_name
from app.agent.orchestrator import _unused_mention_skills
from app.api import mention_skills
from app.api.mention_skills import (
    MAX_MENTION_SKILLS,
    normalize_skill_name,
    resolve_skill_mentions,
)


def _make_skill(
    workspace: Path,
    name: str,
    body: str,
    *,
    kind: str = "knowledge",
    with_script: bool = False,
    description: str = "",
) -> Path:
    """在工作区 `.divine/skills/<name>/` 下造一个技能。"""
    skill_dir = workspace / ".divine" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        "---",
        f"name: {name}",
        f"description: {description or f'{name} 技能'}",
        f"type: {kind}",
        "---",
        "",
        body,
        "",
    ]
    (skill_dir / "SKILL.md").write_text("\n".join(frontmatter), encoding="utf-8")
    if with_script:
        scripts = skill_dir / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    return skill_dir


def test_knowledge_skill_body_is_inlined(tmp_path):
    _make_skill(tmp_path, "tmp-steps", "步骤一：先做 A。\n步骤二：再做 B。")

    result = resolve_skill_mentions(["tmp-steps"], tmp_path)

    assert result.names == ["tmp-steps"]
    assert result.skills[0].type == "knowledge"
    assert result.skills[0].inlined is True
    assert "步骤一：先做 A。" in result.block
    # 强注入：不依赖 agent 自行 load_skill，但仍要保留“别再加载”的约束
    assert "不要再调用 load_skill" in result.block
    assert result.degraded == []
    assert result.invalid == []


def test_executable_skill_injects_tool_contract(tmp_path):
    _make_skill(
        tmp_path,
        "tmp-script",
        "按参数生成报表。",
        kind="executable",
        with_script=True,
    )

    result = resolve_skill_mentions(["tmp-script"], tmp_path)

    assert result.skills[0].type == "executable"
    assert result.skills[0].tool_name == _skill_tool_name("tmp-script")
    assert f"工具 {_skill_tool_name('tmp-script')}" in result.block
    assert "命令行参数" in result.block


def test_normalize_strips_skill_prefix():
    assert normalize_skill_name("  skill:demo  ") == "demo"
    assert normalize_skill_name("skill:skill:demo") == "demo"
    assert normalize_skill_name("demo") == "demo"


def test_skill_prefix_is_not_part_of_name(tmp_path):
    _make_skill(tmp_path, "tmp-demo", "正文。")

    result = resolve_skill_mentions(["skill:tmp-demo"], tmp_path)

    assert result.names == ["tmp-demo"]


def test_missing_skill_is_dropped_from_injection(tmp_path):
    _make_skill(tmp_path, "tmp-demo", "正文。")

    result = resolve_skill_mentions(["tmp-ghost", "skill: tmp-ghost"], tmp_path)

    # 去重后只剩一个失效技能，且不进入生效清单
    assert result.invalid == ["tmp-ghost"]
    assert result.names == []
    assert "已忽略" in result.block


def test_too_many_skills_are_capped(tmp_path):
    names = [f"tmp-skill-{index}" for index in range(MAX_MENTION_SKILLS + 1)]
    for name in names:
        _make_skill(tmp_path, name, "正文。")

    result = resolve_skill_mentions(names, tmp_path)

    assert result.names == names[:MAX_MENTION_SKILLS]
    assert result.dropped == names[MAX_MENTION_SKILLS:]
    assert "已忽略" in result.block


def test_over_budget_skill_degrades_to_load_skill(monkeypatch, tmp_path):
    monkeypatch.setattr(mention_skills, "MAX_SKILL_BODY_CHARS", 5)
    _make_skill(tmp_path, "tmp-long", "很长很长的正文内容，肯定超过预算。")

    result = resolve_skill_mentions(["tmp-long"], tmp_path)

    assert result.degraded == ["tmp-long"]
    assert result.skills[0].inlined is False
    assert 'load_skill("tmp-long")' in result.block
    assert "很长很长的正文内容" not in result.block


def test_unknown_workspace_still_reports_invalid():
    result = resolve_skill_mentions(["tmp-demo"], None)

    assert result.invalid == ["tmp-demo"]
    assert result.names == []
    # 失效技能仍会以“已忽略”硬指令形式告知模型，避免它假装用了
    assert "已忽略：tmp-demo" in result.block


class _FakeMessage:
    def __init__(self, *, tool_calls=None, type="ai", name=""):
        self.tool_calls = tool_calls or []
        self.type = type
        self.name = name


def test_unused_mention_skills_flags_missing_calls():
    messages = [_FakeMessage(tool_calls=[{"name": "read_file", "args": {}}])]

    assert _unused_mention_skills(messages, frozenset({"tmp-demo"})) == ["tmp-demo"]


def test_unused_mention_skills_accepts_load_skill_and_executable_tool():
    messages = [
        _FakeMessage(tool_calls=[{"name": "load_skill", "args": {"name": "know"}}]),
        _FakeMessage(
            tool_calls=[
                {"name": _skill_tool_name("run"), "args": {"args": ["--x"]}}
            ]
        ),
    ]

    unused = _unused_mention_skills(messages, frozenset({"know", "run"}))

    assert unused == []


def test_unused_mention_skills_reads_tool_message_fallback():
    messages = [_FakeMessage(type="tool", name=_skill_tool_name("runner"))]

    assert _unused_mention_skills(messages, frozenset({"runner"})) == []


def test_unused_mention_skills_noop_without_mentions():
    assert _unused_mention_skills([_FakeMessage()], frozenset()) == []
