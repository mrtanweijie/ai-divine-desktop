from app.skills import discover_importable_skills, skill_registry


def test_skill_registry_refresh_empty(tmp_path):
    skills = skill_registry.refresh(tmp_path)
    assert isinstance(skills, list)


def test_discover_importable_skills_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert discover_importable_skills(tmp_path) == []
