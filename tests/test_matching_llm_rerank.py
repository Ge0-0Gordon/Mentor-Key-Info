import json

from match_mentors import parse_args, run_match
from mentor_agent.matching.formatter import to_product_dict
from mentor_agent.matching.reranker import build_rerank_messages, rerank_candidates_with_llm
from mentor_agent.matching.schemas import MentorCandidateCard, StudentProfile


class FakeModel:
    def __init__(self, payload=None, *, exc=None):
        self.payload = payload
        self.exc = exc
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.exc:
            raise self.exc
        return json.dumps(self.payload, ensure_ascii=False)


def _cards(count=3):
    return [
        MentorCandidateCard(
            mentor_id=f"service_mentor:{idx}",
            name=f"导师{idx}",
            city="上海",
            industries=["互联网"],
            companies=["相关公司"],
            roles=["产品经理"],
            skills=["简历优化"],
            target_mentees=["留学生"],
            summary=f"导师{idx}简介",
            rule_score=100 - idx,
            final_score=100 - idx,
        )
        for idx in range(1, count + 1)
    ]


def _mentor_row(idx: int, *, company: str, role: str, skill: str) -> dict:
    return {
        "schema_version": "simple-v1",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": f"service_mentor:{idx}",
        "record_hash": f"{idx}" * 64,
        "source": {"file": "synthetic.xlsx", "sheet": "服务导师", "row": idx + 1},
        "original_fields": {
            "序号": idx,
            "导师姓名": f"导师{idx}",
            "性别": None,
            "城市": "上海",
            "职业年限": 8 + idx,
            "可辅导学员职级": "留学生 应届生",
            "行业标签": "互联网",
            "从业经历": f"资料中出现{company}相关项目。",
            "背景经验": f"擅长{skill}。",
        },
        "extraction": {
            "industries": ["互联网"],
            "companies": [company],
            "roles": [role],
            "skills": [skill],
            "credentials": [],
            "education": [],
            "target_mentees": ["留学生"],
            "highlights": [],
            "keywords": [company, role, skill],
            "summary": f"覆盖{company}{role}方向。",
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


def _write_mentor_results(path):
    rows = [
        _mentor_row(1, company="字节跳动", role="产品经理", skill="简历优化"),
        _mentor_row(2, company="美团", role="产品经理", skill="模拟面试"),
        _mentor_row(3, company="腾讯", role="数据分析", skill="职业规划"),
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_llm_rerank_success_changes_order():
    model = FakeModel(
        {
            "reranked_results": [
                {"mentor_id": "service_mentor:3", "rank": 1, "llm_fit_score": 95, "rerank_note": "更匹配"},
                {"mentor_id": "service_mentor:1", "rank": 2, "llm_fit_score": 90, "rerank_note": ""},
                {"mentor_id": "service_mentor:2", "rank": 3, "llm_fit_score": 88, "rerank_note": None},
            ]
        }
    )
    result = rerank_candidates_with_llm(StudentProfile(raw_query="query"), _cards(3), model, top_k=3)

    assert result.success is True
    assert result.fallback_used is False
    assert result.reranked_ids[:3] == ["service_mentor:3", "service_mentor:1", "service_mentor:2"]
    assert model.calls == 1


def test_llm_rerank_accepts_compact_ordered_ids():
    model = FakeModel(
        {
            "ordered_mentor_ids": ["service_mentor:3", "service_mentor:1", "service_mentor:2"],
            "scores": [96, 90, 88],
        }
    )
    result = rerank_candidates_with_llm(StudentProfile(raw_query="query"), _cards(3), model, top_k=3)

    assert result.success is True
    assert result.fallback_used is False
    assert result.reranked_ids[:3] == ["service_mentor:3", "service_mentor:1", "service_mentor:2"]
    assert result.items[0].llm_fit_score == 96


def test_build_rerank_messages_uses_compact_payload():
    messages = build_rerank_messages(StudentProfile(raw_query="query"), _cards(10), top_k=10)
    combined = "\n".join(message["content"] for message in messages)

    assert "ordered_mentor_ids" in combined
    assert "candidate_mentors" not in combined
    assert '"display"' not in combined
    assert len(combined) < 4500


def test_llm_rerank_invalid_outputs_fallback():
    cases = [
        {"reranked_results": [{"mentor_id": "service_mentor:404", "rank": 1}]},
        {"reranked_results": [{"mentor_id": "service_mentor:1", "rank": 1}, {"mentor_id": "service_mentor:1", "rank": 2}]},
        "not-json",
    ]
    for payload in cases:
        model = FakeModel(payload if isinstance(payload, dict) else None)
        if payload == "not-json":
            model.invoke = lambda messages: "not-json"  # type: ignore[method-assign]
        result = rerank_candidates_with_llm(StudentProfile(raw_query="query"), _cards(3), model, top_k=2)
        assert result.success is False
        assert result.fallback_used is True
        assert result.reranked_ids == ["service_mentor:1", "service_mentor:2"]
        assert result.error_message


def test_llm_rerank_exception_fallback_and_note_sanitized():
    exception_result = rerank_candidates_with_llm(
        StudentProfile(raw_query="query"),
        _cards(3),
        FakeModel(exc=RuntimeError("Authorization token failed")),
        top_k=2,
    )
    assert exception_result.fallback_used is True
    assert "Authorization" not in (exception_result.error_message or "")

    model = FakeModel(
        {
            "reranked_results": [
                {"mentor_id": "service_mentor:1", "rank": 1, "llm_fit_score": 90, "rerank_note": "曾就职相关公司"},
                {"mentor_id": "service_mentor:2", "rank": 2, "llm_fit_score": 80, "rerank_note": ""},
            ]
        }
    )
    clean_result = rerank_candidates_with_llm(StudentProfile(raw_query="query"), _cards(2), model, top_k=2)
    assert clean_result.success is True
    assert clean_result.forbidden_removed is True
    assert "曾就职" not in (clean_result.items[0].rerank_note or "")


def test_run_match_rerank_none_and_llm_report(tmp_path):
    mentors = _write_mentor_results(tmp_path / "mentor_results.jsonl")
    none_result, _ = run_match(
        mentors_path=mentors,
        query="我是留学生，想找字节产品经理，需要简历优化",
        top_k=2,
        rerank="none",
    )
    none_product = to_product_dict(none_result)
    assert none_product["rerank"]["enabled"] is False

    model = FakeModel(
        {
            "reranked_results": [
                {"mentor_id": "service_mentor:2", "rank": 1, "llm_fit_score": 93, "rerank_note": "短备注"},
                {"mentor_id": "service_mentor:1", "rank": 2, "llm_fit_score": 90, "rerank_note": ""},
            ]
        }
    )
    report_path = tmp_path / "rerank_report.md"
    llm_result, markdown = run_match(
        mentors_path=mentors,
        query="我是留学生，想找字节产品经理，需要简历优化",
        top_k=2,
        rerank="llm",
        rerank_candidate_k=2,
        model_client=model,
        rerank_report_path=report_path,
    )
    product = to_product_dict(llm_result)
    assert product["rerank"]["enabled"] is True
    assert product["rerank"]["success"] is True
    assert product["results"][0]["display"]["mentor_id"] == "service_mentor:2"
    assert product["results"][0]["debug"]["llm_rank"] == 1
    assert product["results"][0]["debug"]["llm_fit_score"] == 93
    assert "reason" not in markdown.lower()

    report = report_path.read_text(encoding="utf-8")
    assert "Student Input" in report
    assert "Rule Ranking Before LLM Rerank" in report
    assert "LLM Rerank Result" in report
    assert "Final Recommended Mentor Cards" in report
    assert "曾就职" not in report


def test_parse_args_has_rerank_options(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["match_mentors.py", "--mentors", "dummy.jsonl", "--query", "query"],
    )
    args = parse_args()

    assert args.rerank == "none"
    assert args.rerank_candidate_k == 10
    assert args.rerank_timeout == 8
