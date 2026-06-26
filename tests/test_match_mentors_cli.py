import json

from match_mentors import _profile_from_json, parse_args, run_match
from mentor_agent.matching.formatter import to_product_dict


def test_run_match_returns_json_ready_result(tmp_path):
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(
        json.dumps(
            {
                "companies": [{"canonical": "美团", "aliases": ["美团点评"]}],
                "roles": [{"canonical": "产品经理", "aliases": ["产品"]}],
                "skills": [{"canonical": "模拟面试", "aliases": ["面试辅导"]}],
                "stages": [{"canonical": "应届生", "aliases": ["校招"]}],
                "industries": [{"canonical": "互联网", "aliases": ["大厂"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mentors_path = tmp_path / "mentor_results.jsonl"
    row = {
        "schema_version": "simple-v1",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": "service_mentor:1",
        "record_hash": "b" * 64,
        "source": {"file": "synthetic.xlsx", "sheet": "服务导师", "row": 2},
        "original_fields": {
            "序号": 1,
            "导师姓名": "匿名导师",
            "性别": None,
            "城市": "北京",
            "职业年限": 8,
            "可辅导学员职级": "应届生",
            "行业标签": "互联网",
            "从业经历": "资料中出现美团产品项目。",
            "背景经验": "可做模拟面试。",
        },
        "extraction": {
            "industries": ["互联网"],
            "companies": ["美团"],
            "roles": ["产品经理"],
            "skills": ["模拟面试"],
            "credentials": [],
            "education": [],
            "target_mentees": ["应届生"],
            "highlights": [],
            "keywords": ["美团", "产品经理", "模拟面试"],
            "summary": "覆盖互联网产品方向。",
        },
        "processing": {
            "status": "success",
            "attempt_count": 1,
            "processed_at": "2026-06-25T00:00:00Z",
            "model_service_name": "fake",
            "model_name": "fake",
            "latency_ms": 1,
        },
    }
    mentors_path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")

    result, markdown = run_match(
        mentors_path=mentors_path,
        query="校招想找美团产品经理，做面试辅导",
        top_k=1,
        aliases_path=alias_path,
    )

    assert result.returned_count == 1
    assert result.results[0].display.mentor_id == "service_mentor:1"
    assert result.results[0].display.name
    assert result.results[0].display.city
    assert result.results[0].display.years_experience == 8
    assert result.results[0].display.industries
    assert result.results[0].display.companies
    assert result.results[0].display.roles
    assert result.results[0].display.skills
    assert result.results[0].display.target_mentees
    assert result.results[0].display.summary
    assert result.results[0].debug.final_score >= 0
    assert result.results[0].debug.score_breakdown.final_score >= 0
    assert result.results[0].debug.matched_signals
    assert not hasattr(result.results[0].display, "possible_gap")
    assert "service_mentor:1" in markdown
    assert "reason" not in markdown.lower()
    product = to_product_dict(result)
    assert len(product["all_mentors"]) == 1
    assert product["all_mentors"][0]["display"]["is_recommended"] is True
    assert product["recommendation"]["recommended_mentor_ids"] == ["service_mentor:1"]
    assert product["recommendation"]["scoring_version"] == "recommendation-v1"
    assert set(product["filters"]) == {"companies", "roles", "industries", "skills", "cities"}
    assert set(product["results"][0]) == {"display", "debug"}
    assert "recommendation_reason" not in product["results"][0]["display"]
    assert "possible_gap" not in product["results"][0]["display"]
    dumped = json.dumps(product, ensure_ascii=False)
    for unsafe in ["曾就职", "任职过", "供职", "前员工", "老东家"]:
        assert unsafe not in dumped


def test_default_top_k_is_10(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["match_mentors.py", "--mentors", "dummy.jsonl", "--query", "query"],
    )
    args = parse_args()

    assert args.top_k == 10


def test_student_profile_json_input(tmp_path):
    profile_path = tmp_path / "student_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "student_profile": {
                    "work_years": 0,
                    "target_roles": ["产品经理"],
                    "target_companies": ["美团"],
                    "target_industries": ["互联网"],
                    "needed_help": ["模拟面试"],
                    "current_stage": ["应届生"],
                    "preferred_background": ["大厂"],
                    "keywords": ["产品"],
                    "constraints": {"city": None, "gender": None, "seniority": None},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    profile = _profile_from_json(profile_path)

    assert profile.work_years == 0
    assert profile.target_roles == ["产品经理"]
    assert profile.raw_query
