"""Optional rerank helpers and guardrails.

The MVP keeps customer-facing matching offline by default. These helpers make a
future LLM rerank step testable without allowing it to invent employment claims.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from .schemas import MentorCandidateCard, RerankResponse


UNSAFE_EMPLOYER_PHRASES = ("曾就职", "任职于", "供职于", "前员工", "老东家", "曾任职")


class RerankValidationError(ValueError):
    """Raised when rerank output is not safe to use."""


def build_rerank_prompt(query: str, candidates: list[MentorCandidateCard]) -> str:
    """Build a compact future LLM rerank prompt.

    The prompt is not used by the default CLI path; it documents and tests the
    safe contract for a future online reranker.
    """

    cards = [
        {
            "mentor_id": card.mentor_id,
            "name": card.name,
            "city": card.city,
            "industries": card.industries,
            "companies": card.companies,
            "roles": card.roles,
            "skills": card.skills,
            "target_mentees": card.target_mentees,
            "highlights": card.highlights[:5],
            "summary": card.summary,
            "matched_signals": card.matched_signals.model_dump(),
            "rule_score": card.rule_score,
        }
        for card in candidates
    ]
    payload = {"query": query, "candidate_cards": cards}
    return (
        "你是导师推荐重排器。只基于 candidate_cards 推荐，不要编造。\n"
        "推荐理由必须来自 matched_signals 或 candidate card。\n"
        "companies 只能表述为“资料中出现相关公司/机构”，不能说“曾就职”。\n"
        "只输出 JSON：{\"recommendations\":[{\"mentor_id\":\"...\",\"rank\":1,"
        "\"fit_score\":90,\"fit_reasons\":[],\"possible_gap\":null}]}\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def validate_rerank_response(raw: object, candidates: list[MentorCandidateCard]) -> RerankResponse:
    try:
        response = RerankResponse.model_validate(raw)
    except ValidationError as exc:
        raise RerankValidationError(f"invalid rerank response: {exc}") from exc

    candidate_ids = {card.mentor_id for card in candidates}
    ranks = set()
    for item in response.recommendations:
        if item.mentor_id not in candidate_ids:
            raise RerankValidationError(f"rerank returned unknown mentor_id: {item.mentor_id}")
        if item.rank in ranks:
            raise RerankValidationError(f"duplicate rerank rank: {item.rank}")
        ranks.add(item.rank)
        texts = [*item.fit_reasons, item.possible_gap or ""]
        if any(phrase in text for text in texts for phrase in UNSAFE_EMPLOYER_PHRASES):
            raise RerankValidationError("rerank reason contains unverified employer wording")

    return response


__all__ = [
    "RerankValidationError",
    "UNSAFE_EMPLOYER_PHRASES",
    "build_rerank_prompt",
    "validate_rerank_response",
]
