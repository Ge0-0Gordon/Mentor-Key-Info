"""Output formatting for fast mentor matching."""

from __future__ import annotations

from .schemas import MatchResult, MentorCandidateCard, Recommendation, StudentProfile
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
    recommendations = []
    for rank, card in enumerate(candidate_cards[:top_k], start=1):
        recommendations.append(
            Recommendation(
                mentor_id=card.mentor_id,
                mentor_name=card.name,
                city=card.city,
                summary=card.summary,
                rank=rank,
                match_score=card.rule_score,
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
        recommendations=recommendations,
    )


def _signal_summary(recommendation: Recommendation) -> str:
    parts = []
    signals = recommendation.matched_signals
    for label, items in [
        ("公司/机构", signals.companies),
        ("岗位", signals.roles),
        ("需求", signals.skills),
        ("阶段", signals.target_mentees),
        ("行业", signals.industries),
    ]:
        if items:
            values = "、".join(dict.fromkeys((item.canonical or item.matched_term) for item in items[:3]))
            parts.append(f"{label}:{values}")
    return "; ".join(parts) or "-"


def format_markdown(result: MatchResult) -> str:
    lines = [
        "| rank | mentor_id | 导师 | 城市 | score | matched_signals | reason | possible_gap |",
        "| ---: | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for rec in result.recommendations:
        reason = "；".join(rec.recommendation_reason) or "-"
        gap = rec.possible_gap or "-"
        lines.append(
            f"| {rec.rank} | {rec.mentor_id} | {rec.mentor_name or '-'} | {rec.city or '-'} | "
            f"{rec.match_score:.1f} | "
            f"{_signal_summary(rec)} | {reason} | {gap} |"
        )
    return "\n".join(lines)


__all__ = ["build_match_result", "format_markdown"]
