"""Output formatting for fast mentor matching."""

from __future__ import annotations

from .schemas import (
    MatchDebugInfo,
    MatchItem,
    MatchResult,
    MentorCandidateCard,
    MentorDisplayCard,
    Recommendation,
    StudentProfile,
)
from .scorer import build_reasons, possible_gap


def build_match_result(
    *,
    query: str,
    profile: StudentProfile,
    total_mentors: int,
    candidate_cards: list[MentorCandidateCard],
    top_k: int,
    used_rerank: bool = False,
) -> MatchResult:
    items = []
    recommendations = []
    for rank, card in enumerate(candidate_cards[:top_k], start=1):
        display = MentorDisplayCard(
            rank=rank,
            mentor_id=card.mentor_id,
            name=card.name,
            gender=card.gender,
            city=card.city,
            years_experience=card.years_experience,
            industries=card.industries,
            companies=card.companies,
            roles=card.roles,
            skills=card.skills,
            credentials=card.credentials,
            education=card.education,
            target_mentees=card.target_mentees,
            highlights=card.highlights,
            keywords=card.keywords,
            summary=card.summary,
        )
        debug = MatchDebugInfo(
            final_score=card.final_score,
            score_breakdown=card.score_breakdown,
            matched_signals=card.matched_signals,
            possible_gap=possible_gap(card, profile),
            profile_parse_result=profile,
            recommendation_reason=build_reasons(card),
        )
        items.append(MatchItem(display=display, debug=debug))

        # Backward-compatible internal field. Product output should read
        # results[].display/debug instead of this legacy list.
        recommendations.append(
            Recommendation(
                mentor_id=card.mentor_id,
                mentor_name=card.name,
                city=card.city,
                summary=card.summary,
                rank=rank,
                match_score=card.final_score,
                rule_score=card.rule_score,
                matched_signals=card.matched_signals,
                recommendation_reason=build_reasons(card),
                possible_gap=possible_gap(card, profile),
            )
        )

    return MatchResult(
        query=query,
        student_profile=profile,
        total_mentors=total_mentors,
        candidate_count=len(candidate_cards),
        returned_count=len(recommendations),
        used_rerank=used_rerank,
        results=items,
        recommendations=recommendations,
    )


def _join_values(values: list[str], limit: int = 4) -> str:
    return "、".join(values[:limit]) if values else "-"


def format_markdown(result: MatchResult, *, show_score: bool = False) -> str:
    score_columns = " | final_score" if show_score else ""
    score_header = " | ---:" if show_score else ""
    lines = [
        "| rank | mentor_id | 导师姓名 | 城市 | 职业年限 | 相关行业 | 相关公司/机构 | 岗位/身份 | 擅长方向 | 可辅导人群 | 简介"
        + score_columns
        + " |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---"
        + score_header
        + " |",
    ]
    for item in result.results:
        display = item.display
        score_cell = f" | {item.debug.final_score:.1f}" if show_score else ""
        lines.append(
            f"| {display.rank} | {display.mentor_id} | {display.name or '-'} | "
            f"{display.city or '-'} | {display.years_experience or '-'} | "
            f"{_join_values(display.industries)} | {_join_values(display.companies)} | "
            f"{_join_values(display.roles)} | {_join_values(display.skills)} | "
            f"{_join_values(display.target_mentees)} | {display.summary or '-'}"
            f"{score_cell} |"
        )
    return "\n".join(lines)


def to_product_dict(result: MatchResult) -> dict:
    return {
        "student_profile": result.student_profile.model_dump(mode="json"),
        "results": [
            {
                "display": item.display.model_dump(mode="json"),
                "debug": item.debug.model_dump(mode="json"),
            }
            for item in result.results
        ],
    }


__all__ = ["build_match_result", "format_markdown", "to_product_dict"]
