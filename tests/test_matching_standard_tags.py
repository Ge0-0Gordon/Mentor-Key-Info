"""Phase 2 tests for standard-tag matching and display."""

from __future__ import annotations

from mentor_agent.matching.aliases import AliasIndex
from mentor_agent.matching.formatter import (
    build_match_result,
    format_markdown,
    to_product_dict,
)
from mentor_agent.matching.mentor_index import build_mentor_document
from mentor_agent.matching.schemas import StudentProfile
from mentor_agent.matching.scorer import score_mentor
from mentor_agent.simple_schemas import SimpleMentorResult


def _aliases() -> AliasIndex:
    return AliasIndex(
        {
            "companies": [],
            "roles": [
                {
                    "canonical": "产品经理",
                    "aliases": ["产品", "PM"],
                },
                {
                    "canonical": "人工智能",
                    "aliases": ["AI", "大模型", "Agent"],
                },
            ],
            "skills": [],
            "stages": [],
            "industries": [
                {
                    "canonical": "AI/互联网/IT",
                    "aliases": ["互联网行业", "AI行业"],
                }
            ],
        }
    )


def _result(
    *,
    position_tags: list[dict] | None = None,
    industry_tags: list[dict] | None = None,
    company_tags: list[dict] | None = None,
    raw_keywords: list[str] | None = None,
    roles: list[str] | None = None,
    industries: list[str] | None = None,
) -> SimpleMentorResult:
    return SimpleMentorResult.model_validate(
        {
            "schema_version": "simple-v1",
            "prompt_version": "mentor-simple-tagged-v1",
            "standard_tags_enabled": True,
            "taxonomy_hash": "a" * 64,
            "mentor_id": "service_mentor:standard",
            "record_hash": "b" * 64,
            "source": {
                "file": "synthetic.xlsx",
                "sheet": "服务导师",
                "row": 2,
            },
            "original_fields": {
                "序号": 1,
                "导师姓名": "匿名导师",
                "性别": "未知",
                "城市": "上海",
                "职业年限": 8,
                "可辅导学员职级": "应届生",
                "行业标签": "技术服务",
                "从业经历": "曾任匿名公司业务负责人。",
                "背景经验": "擅长求职辅导。",
            },
            "extraction": {
                "industries": industries or [],
                "companies": [],
                "roles": roles or [],
                "skills": [],
                "credentials": [],
                "education": [],
                "target_mentees": [],
                "highlights": [],
                "keywords": [],
                "industry_tags": industry_tags or [],
                "position_tags": position_tags or [],
                "company_tags": company_tags or [],
                "raw_keywords": raw_keywords or [],
                "review_required": False,
                "review_reasons": [],
                "summary": "提供求职辅导。",
            },
            "processing": {
                "status": "success",
                "attempt_count": 1,
                "processed_at": "2026-06-29T00:00:00Z",
                "model_service_name": "fake",
                "model_name": "fake",
                "latency_ms": 1,
            },
        }
    )


def _position(
    tag: str,
    confidence: float,
    relation_type: str = "firsthand_role",
) -> dict:
    return {
        "tag": tag,
        "relation_type": relation_type,
        "confidence": confidence,
        "raw_keywords": [],
        "evidence": "业务负责人",
    }


def test_index_contains_standard_and_company_search_terms() -> None:
    result = _result(
        position_tags=[_position("产品经理", 0.9)],
        industry_tags=[
            {
                "tag": "AI/互联网/IT",
                "confidence": 0.9,
                "evidence": "技术服务",
            }
        ],
        company_tags=[
            {
                "company_name": "匿名公司",
                "company_type": "互联网公司",
                "industry_tag": "AI/互联网/IT",
                "confidence": 0.9,
                "evidence": "匿名公司",
            }
        ],
        raw_keywords=["产品负责人"],
    )

    document = build_mentor_document(result)

    for term in (
        "产品经理",
        "AI/互联网/IT",
        "匿名公司",
        "互联网公司",
        "产品负责人",
    ):
        assert term in document.search_text


def test_high_confidence_standard_tags_are_preferred_sources() -> None:
    document = build_mentor_document(
        _result(
            position_tags=[_position("产品经理", 0.9)],
            industry_tags=[
                {
                    "tag": "AI/互联网/IT",
                    "confidence": 0.9,
                    "evidence": "技术服务",
                }
            ],
            roles=["产品经理"],
            industries=["AI/互联网/IT"],
        )
    )
    profile = StudentProfile(
        target_roles=["产品经理"],
        target_industries=["AI/互联网/IT"],
    )

    card = score_mentor(document, profile, _aliases())

    assert card.score_breakdown.role_match == 100
    assert card.score_breakdown.industry_match == 100
    assert card.matched_signals.roles[0].source_field == "position_tags.tag"
    assert card.matched_signals.industries[0].source_field == "industry_tags.tag"


def test_low_confidence_and_raw_keywords_are_weak_signals() -> None:
    low_card = score_mentor(
        build_mentor_document(
            _result(position_tags=[_position("人工智能", 0.69)])
        ),
        StudentProfile(target_roles=["人工智能"]),
        _aliases(),
    )
    raw_card = score_mentor(
        build_mentor_document(_result(raw_keywords=["人工智能"])),
        StudentProfile(target_roles=["人工智能"]),
        _aliases(),
    )

    assert low_card.score_breakdown.role_match == 65
    assert low_card.matched_signals.roles[0].source_field == "position_tags.tag"
    assert raw_card.score_breakdown.role_match == 60
    assert raw_card.matched_signals.roles[0].source_field == "raw_keywords"


def test_relation_type_does_not_change_first_version_score() -> None:
    profile = StudentProfile(target_roles=["产品经理"])
    firsthand = score_mentor(
        build_mentor_document(
            _result(
                position_tags=[
                    _position("产品经理", 0.9, "firsthand_role")
                ]
            )
        ),
        profile,
        _aliases(),
    )
    recruited = score_mentor(
        build_mentor_document(
            _result(
                position_tags=[
                    _position(
                        "产品经理",
                        0.9,
                        "recruited_or_evaluated",
                    )
                ]
            )
        ),
        profile,
        _aliases(),
    )

    assert firsthand.final_score == recruited.final_score
    assert firsthand.score_breakdown.role_match == recruited.score_breakdown.role_match


def test_formatter_displays_standard_tags_relation_and_match_source() -> None:
    profile = StudentProfile(target_roles=["产品经理"])
    card = score_mentor(
        build_mentor_document(
            _result(position_tags=[_position("产品经理", 0.9)])
        ),
        profile,
        _aliases(),
    )
    result = build_match_result(
        query="找产品经理导师",
        profile=profile,
        total_mentors=1,
        candidate_cards=[card],
        top_k=1,
    )

    markdown = format_markdown(result)
    product = to_product_dict(result)

    assert "产品经理 (firsthand_role, 0.90)" in markdown
    assert product["results"][0]["display"]["position_tags"][0]["tag"] == "产品经理"
    assert (
        product["results"][0]["debug"]["matched_signals"]["roles"][0][
            "source_field"
        ]
        == "position_tags.tag"
    )
