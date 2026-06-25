import json
from pathlib import Path

from mentor_agent.matching.aliases import AliasIndex
from mentor_agent.matching.formatter import build_match_result
from mentor_agent.matching.mentor_index import load_mentor_documents
from mentor_agent.matching.scorer import rank_candidates, score_mentor
from mentor_agent.matching.student_profile import extract_student_profile


def _write_aliases(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "companies": [{"canonical": "字节跳动", "aliases": ["字节", "ByteDance"]}],
                "roles": [{"canonical": "产品经理", "aliases": ["PM", "产品"]}],
                "skills": [{"canonical": "简历优化", "aliases": ["改简历"]}],
                "stages": [{"canonical": "留学生", "aliases": ["海归"]}],
                "industries": [{"canonical": "互联网", "aliases": ["大厂"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _result(
    *,
    mentor_id: str,
    companies: list[str] | None = None,
    roles: list[str] | None = None,
    skills: list[str] | None = None,
    target_mentees: list[str] | None = None,
    industries: list[str] | None = None,
    keywords: list[str] | None = None,
    career_history: str = "",
) -> dict:
    return {
        "schema_version": "simple-v1",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": mentor_id,
        "record_hash": "a" * 64,
        "source": {"file": "synthetic.xlsx", "sheet": "服务导师", "row": 2},
        "original_fields": {
            "序号": mentor_id.rsplit(":", 1)[-1],
            "导师姓名": f"导师{mentor_id}",
            "性别": "未知",
            "城市": "上海",
            "职业年限": 10,
            "可辅导学员职级": "留学生 应届生",
            "行业标签": "互联网",
            "从业经历": career_history,
            "背景经验": "擅长简历优化和模拟面试",
        },
        "extraction": {
            "industries": industries or [],
            "companies": companies or [],
            "roles": roles or [],
            "skills": skills or [],
            "credentials": [],
            "education": [],
            "target_mentees": target_mentees or [],
            "highlights": [],
            "keywords": keywords or [],
            "summary": "导师资料覆盖互联网产品和求职辅导。",
        },
        "processing": {
            "status": "success",
            "attempt_count": 1,
            "processed_at": "2026-06-25T00:00:00Z",
            "model_service_name": "fake",
            "model_name": "fake",
            "latency_ms": 10,
        },
    }


def _write_results(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_score_uses_structured_fields_and_reasons_avoid_employer_claim(tmp_path):
    aliases = AliasIndex.from_path(_write_aliases(tmp_path / "aliases.json"))
    result_path = _write_results(
        tmp_path / "mentor_results.jsonl",
        [
            _result(
                mentor_id="service_mentor:1",
                companies=["字节跳动"],
                roles=["产品经理"],
                skills=["简历优化"],
                target_mentees=["留学生"],
                industries=["互联网"],
            )
        ],
    )
    document = load_mentor_documents(result_path)[0]
    profile = extract_student_profile("我是留学生，想找字节产品经理，需要改简历", aliases)

    card = score_mentor(document, profile, aliases)

    assert card.rule_score > 90
    assert card.matched_signals.companies[0].canonical == "字节跳动"
    match_result = build_match_result(
        query=profile.raw_query,
        profile=profile,
        total_mentors=1,
        candidate_cards=[card],
        top_k=1,
    )
    reasons = " ".join(match_result.recommendations[0].recommendation_reason)
    assert "资料中出现相关公司" not in reasons
    assert "相关信号" in reasons
    assert "曾就职" not in reasons


def test_raw_text_fallback_rescues_simple_extraction_miss(tmp_path):
    aliases = AliasIndex.from_path(_write_aliases(tmp_path / "aliases.json"))
    result_path = _write_results(
        tmp_path / "mentor_results.jsonl",
        [
            _result(
                mentor_id="service_mentor:1",
                career_history="曾服务多个字节跳动相关项目，负责产品面试辅导。",
            )
        ],
    )
    document = load_mentor_documents(result_path)[0]
    profile = extract_student_profile("想找字节产品方向，帮我改简历", aliases)

    card = score_mentor(document, profile, aliases)

    assert card.matched_signals.companies[0].source_field == "raw_text"
    assert 0 < card.score_breakdown.company_match < 100


def test_rank_candidates_returns_top_k_order(tmp_path):
    aliases = AliasIndex.from_path(_write_aliases(tmp_path / "aliases.json"))
    result_path = _write_results(
        tmp_path / "mentor_results.jsonl",
        [
            _result(mentor_id="service_mentor:1", companies=["字节跳动"], roles=["产品经理"], skills=["简历优化"]),
            _result(mentor_id="service_mentor:2", roles=["产品经理"]),
        ],
    )
    documents = load_mentor_documents(result_path)
    profile = extract_student_profile("留学生目标字节产品经理，需要简历优化", aliases)

    cards = rank_candidates(documents, profile, aliases, candidate_pool_size=2)

    assert [card.mentor_id for card in cards] == ["service_mentor:1", "service_mentor:2"]
