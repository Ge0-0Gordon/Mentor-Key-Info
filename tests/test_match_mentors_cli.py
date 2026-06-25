import json

from match_mentors import run_match


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
    assert result.recommendations[0].mentor_id == "service_mentor:1"
    assert "service_mentor:1" in markdown
    assert "曾就职" not in result.model_dump_json(ensure_ascii=False)
