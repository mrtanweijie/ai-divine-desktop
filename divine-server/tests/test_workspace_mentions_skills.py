"""技能候选（P1b / B1、B4）测试。

覆盖：会话工作区作用域、分节与排序、匹配分级、上限截断、TTL 缓存，
以及「候选扫描不污染 skill_registry 单例状态」这条关键回归。

另覆盖 `GET /api/workspace/skill-names`（气泡渲染用的**名称全集**）：它必须绕过
`SKILL_LIMIT` 截断，否则超出弹层上限的真技能会被降级成普通文本。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import workspace_files
from app.skills import skill_registry


def _write_skill(
    workspace: Path,
    name: str,
    *,
    description: str = "",
    skill_type: str = "knowledge",
    with_script: bool = False,
) -> None:
    skill_dir = workspace / ".divine" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    front = ["---", f"name: {name}", f"type: {skill_type}"]
    if description:
        front.append(f"description: {description}")
    front.append("---")
    (skill_dir / "SKILL.md").write_text(
        "\n".join(front) + "\n正文内容\n", encoding="utf-8"
    )
    if with_script:
        # 有脚本时 _parse_skill 会把类型提升为 executable
        (skill_dir / "script.py").write_text("print('ok')\n", encoding="utf-8")


def _reset(monkeypatch, workspace: Path) -> None:
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: workspace)
    monkeypatch.setattr(
        workspace_files, "resolve_workspace", lambda session_id=None: workspace
    )
    workspace_files._index_cache.clear()
    workspace_files._skill_cache.clear()


def _names(payload: dict) -> list[str]:
    return [item["path"] for item in payload["items"]]


def test_skill_candidates_shape_and_sections(monkeypatch, tmp_path):
    _write_skill(tmp_path, "note-keeper", description="整理会议纪要")
    _write_skill(tmp_path, "deck-builder", skill_type="executable", with_script=True)
    _reset(monkeypatch, tmp_path)

    payload = workspace_files.list_mentions(
        q=None, session_id=None, kinds="skill", limit=20
    )

    entry = next(item for item in payload["items"] if item["path"] == "note-keeper")
    assert entry == {
        "kind": "skill",
        "path": "note-keeper",
        "name": "note-keeper",
        "type": "knowledge",
        "source": "project",
        "description": "整理会议纪要",
        "version": "0.0.0",
    }
    # 知识技能整段排在能力技能之前（弹层分节顺序）
    types = [item["type"] for item in payload["items"]]
    last_knowledge = max(i for i, t in enumerate(types) if t == "knowledge")
    first_executable = min(i for i, t in enumerate(types) if t in {"executable", "mcp"})
    assert last_knowledge < first_executable


def test_skill_match_grading(monkeypatch, tmp_path):
    _write_skill(tmp_path, "photo-editorial", description="照片编辑风")
    _write_skill(tmp_path, "editorial-notes")
    _write_skill(tmp_path, "random-thing", description="photo 相关说明")
    _reset(monkeypatch, tmp_path)

    exact = workspace_files.list_mentions(
        q="photo-editorial", session_id=None, kinds="skill", limit=20
    )
    assert _names(exact)[0] == "photo-editorial"

    prefix = workspace_files.list_mentions(
        q="edit", session_id=None, kinds="skill", limit=20
    )
    assert set(_names(prefix)) >= {"photo-editorial", "editorial-notes"}

    # 名称前缀命中优先于描述命中
    mixed = workspace_files.list_mentions(
        q="photo", session_id=None, kinds="skill", limit=20
    )
    assert _names(mixed)[0] == "photo-editorial"

    # 子序列兜底
    fuzzy = workspace_files.list_mentions(
        q="pted", session_id=None, kinds="skill", limit=20
    )
    assert "photo-editorial" in _names(fuzzy)


def test_skill_candidates_follow_session_workspace(monkeypatch, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    _write_skill(project_a, "alpha-report")
    _write_skill(project_b, "beta-report")
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: project_a)
    monkeypatch.setattr(
        workspace_files,
        "resolve_workspace",
        lambda session_id=None: project_b if session_id == "B" else project_a,
    )
    workspace_files._skill_cache.clear()

    in_a = workspace_files.list_mentions(
        q="report", session_id="A", kinds="skill", limit=20
    )
    in_b = workspace_files.list_mentions(
        q="report", session_id="B", kinds="skill", limit=20
    )

    assert "alpha-report" in _names(in_a)
    assert "beta-report" not in _names(in_a)
    assert "beta-report" in _names(in_b)
    assert "alpha-report" not in _names(in_b)


def test_skill_limit_truncates(monkeypatch, tmp_path):
    for index in range(12):
        _write_skill(tmp_path, f"skill-{index:02d}")
    _reset(monkeypatch, tmp_path)

    payload = workspace_files.list_mentions(
        q="skill-", session_id=None, kinds="skill", limit=50
    )

    assert len(payload["items"]) == workspace_files.SKILL_LIMIT


def test_skill_candidates_do_not_pollute_registry(monkeypatch, tmp_path):
    _write_skill(tmp_path, "alpha-report")
    _reset(monkeypatch, tmp_path)
    # 制造一个「agent 侧」的单例状态作为哨兵
    skill_registry.refresh(project_root=tmp_path / "other-workspace")
    before = dict(skill_registry._skills)

    workspace_files.list_mentions(q="report", session_id=None, kinds="skill", limit=20)

    assert skill_registry._skills == before


def test_skill_cache_hits_within_ttl(monkeypatch, tmp_path):
    _write_skill(tmp_path, "alpha-report")
    _reset(monkeypatch, tmp_path)
    calls = {"n": 0}
    original = workspace_files._scan_skills

    def counted(root: Path):
        calls["n"] += 1
        return original(root)

    monkeypatch.setattr(workspace_files, "_scan_skills", counted)

    workspace_files.list_mentions(q="report", session_id=None, kinds="skill", limit=20)
    workspace_files.list_mentions(q="report", session_id=None, kinds="skill", limit=20)
    assert calls["n"] == 1

    monkeypatch.setattr(workspace_files, "SKILL_TTL_SECONDS", -1.0)
    workspace_files.list_mentions(q="report", session_id=None, kinds="skill", limit=20)
    assert calls["n"] == 2


def test_skill_and_file_mixed_kinds(monkeypatch, tmp_path):
    _write_skill(tmp_path, "alpha-report")
    (tmp_path / "report.md").write_text("x\n", encoding="utf-8")
    _reset(monkeypatch, tmp_path)

    payload = workspace_files.list_mentions(
        q="report", session_id=None, kinds="file,skill", limit=20
    )

    kinds = [item["kind"] for item in payload["items"]]
    assert "file" in kinds
    assert "skill" in kinds
    # 混排时文件在前、技能在后
    assert kinds.index("skill") > 0


@pytest.mark.skipif(
    not workspace_files._PINYIN_AVAILABLE, reason="未安装 pypinyin（可选增强依赖）"
)
def test_skill_pinyin_initials_match(monkeypatch, tmp_path):
    _write_skill(tmp_path, "笔记整理", description="会议纪要归档")
    _reset(monkeypatch, tmp_path)

    by_name = workspace_files.list_mentions(
        q="bj", session_id=None, kinds="skill", limit=20
    )
    assert "笔记整理" in _names(by_name)

    # 描述拼音也能命中（名称部分不匹配）
    by_description = workspace_files.list_mentions(
        q="hyj", session_id=None, kinds="skill", limit=20
    )
    assert "笔记整理" in _names(by_description)


def test_initials_skips_ascii_text():
    assert workspace_files._initials("photo-editorial") == ""
    assert workspace_files._initials("") == ""


# --- 气泡渲染用的名称全集：GET /api/workspace/skill-names ---


def test_skill_names_are_not_truncated(monkeypatch, tmp_path):
    """名称全集必须完整：候选接口只给前 SKILL_LIMIT 条，拿它做全集会误判真技能。"""
    total = workspace_files.SKILL_LIMIT + 4
    written = [f"skill-{index:02d}" for index in range(total)]
    for name in written:
        _write_skill(tmp_path, name)
    _reset(monkeypatch, tmp_path)

    payload = workspace_files.list_skill_names(session_id=None)

    assert payload["workspace"] == str(tmp_path)
    # 全集里还会有内置/用户级技能（与 agent 侧同源），故只断言「包含写入项」
    assert set(written) <= set(payload["names"])
    assert len(payload["names"]) > workspace_files.SKILL_LIMIT
    assert payload["names"] == sorted(payload["names"])
    # 候选接口的截断行为不变（两个端点服务不同用途）
    candidates = workspace_files.list_mentions(
        q="skill-", session_id=None, kinds="skill", limit=50
    )
    assert len(_names(candidates)) == workspace_files.SKILL_LIMIT


def test_skill_names_missing_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(
        workspace_files, "resolve_workspace", lambda session_id=None: None
    )

    assert workspace_files.list_skill_names(session_id=None) == {
        "workspace": None,
        "names": [],
    }


def test_skill_names_reuse_candidate_cache(monkeypatch, tmp_path):
    """与候选接口共用 _get_skills 缓存：气泡渲染不额外扫盘。"""
    _write_skill(tmp_path, "alpha-report")
    _reset(monkeypatch, tmp_path)
    calls = {"n": 0}
    original = workspace_files._scan_skills

    def counted(root: Path):
        calls["n"] += 1
        return original(root)

    monkeypatch.setattr(workspace_files, "_scan_skills", counted)

    workspace_files.list_mentions(q="report", session_id=None, kinds="skill", limit=20)
    workspace_files.list_skill_names(session_id=None)

    assert calls["n"] == 1


def test_skill_names_route(monkeypatch, tmp_path):
    _write_skill(tmp_path, "alpha-report")
    _write_skill(tmp_path, "笔记整理")
    _reset(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(workspace_files.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/workspace/skill-names")

    assert response.status_code == 200
    names = response.json()["names"]
    assert "alpha-report" in names
    assert "笔记整理" in names
    assert names == sorted(names)


def test_mentions_route_serves_skill_candidates(monkeypatch, tmp_path):
    _write_skill(tmp_path, "alpha-report")
    monkeypatch.setattr(
        workspace_files, "resolve_workspace", lambda session_id=None: tmp_path
    )
    workspace_files._skill_cache.clear()

    app = FastAPI()
    app.include_router(workspace_files.router, prefix="/api")
    client = TestClient(app)

    data = client.get(
        "/api/workspace/mentions", params={"kinds": "skill", "q": "alpha"}
    ).json()

    assert [item["path"] for item in data["items"]] == ["alpha-report"]
    assert data["items"][0]["kind"] == "skill"
