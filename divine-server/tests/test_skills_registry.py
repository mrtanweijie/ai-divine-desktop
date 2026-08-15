from app.skills import discover_importable_skills, skill_registry


def test_skill_registry_refresh_empty(tmp_path):
    skills = skill_registry.refresh(tmp_path)
    assert isinstance(skills, list)


def test_skill_registry_parses_project_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    skill_dir = project / ".divine" / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: 测试技能\n---\n\n正文",
        encoding="utf-8",
    )

    skills = skill_registry.refresh(project)
    assert [skill["name"] for skill in skills] == ["hello"]


def test_skill_registry_scans_all_project_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    for project, name in ((first, "alpha"), (second, "beta")):
        skill_dir = project / ".divine" / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: 测试技能\n---\n\n正文",
            encoding="utf-8",
        )

    skills = skill_registry.refresh(project_roots=[first, second])
    assert sorted(skill["name"] for skill in skills) == ["alpha", "beta"]


def test_skill_registry_uninstalls_from_other_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    skill_dir = project / ".divine" / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: 测试技能\n---\n\n正文",
        encoding="utf-8",
    )

    result = skill_registry.uninstall(
        "hello", project_roots=[project]
    )
    assert result["ok"] is True
    assert not skill_dir.exists()


def test_discover_importable_skills_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert discover_importable_skills(tmp_path) == []
