import pytest

from mentor_agent.matching.reranker import RerankValidationError, validate_rerank_response
from mentor_agent.matching.schemas import MentorCandidateCard


def _card(mentor_id: str = "service_mentor:1") -> MentorCandidateCard:
    return MentorCandidateCard(mentor_id=mentor_id, rule_score=80)


def test_validate_rerank_response_accepts_known_candidate():
    response = validate_rerank_response(
        {
            "recommendations": [
                {
                    "mentor_id": "service_mentor:1",
                    "rank": 1,
                    "fit_score": 90,
                    "fit_reasons": ["资料中出现相关公司/机构信号"],
                    "possible_gap": None,
                }
            ]
        },
        [_card()],
    )

    assert response.recommendations[0].mentor_id == "service_mentor:1"


def test_validate_rerank_response_rejects_unknown_candidate():
    with pytest.raises(RerankValidationError, match="unknown mentor_id"):
        validate_rerank_response(
            {"recommendations": [{"mentor_id": "service_mentor:404", "rank": 1, "fit_score": 90}]},
            [_card()],
        )


def test_validate_rerank_response_rejects_unverified_employer_wording():
    with pytest.raises(RerankValidationError, match="employer wording"):
        validate_rerank_response(
            {
                "recommendations": [
                    {
                        "mentor_id": "service_mentor:1",
                        "rank": 1,
                        "fit_score": 90,
                        "fit_reasons": ["导师曾就职字节，适合推荐"],
                    }
                ]
            },
            [_card()],
        )
