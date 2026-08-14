from app.resume_themes.models import ResumeData


def test_resume_data_from_dict_normalizes_basics_and_work():
    resume = ResumeData.from_dict(
        {
            "basics": {"name": "张三", "title": "工程师"},
            "work": [
                {
                    "company": "ACME",
                    "position": "后端工程师",
                    "startDate": "2020",
                    "endDate": "2025",
                }
            ],
            "skills": [{"name": "Python", "level": 4}],
        }
    )
    assert resume.name == "张三"
    assert resume.title == "工程师"
    assert resume.experiences[0].company == "ACME"
    assert resume.skills[0].level == 80
