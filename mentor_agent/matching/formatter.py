"""Output formatting for fast mentor matching."""

from __future__ import annotations

from .schemas import (
    MatchDebugInfo,
    MatchItem,
    MatchRerankMetadata,
    MatchResult,
    MatchSemanticMetadata,
    MentorCandidateCard,
    MentorDisplayCard,
    Recommendation,
    StudentProfile,
)
from .reranker import RerankResult
from .scorer import build_reasons, possible_gap


def build_match_result(
    *,
    query: str,
    profile: StudentProfile,
    total_mentors: int,
    candidate_cards: list[MentorCandidateCard],
    top_k: int,
    used_rerank: bool = False,
    rule_candidate_cards: list[MentorCandidateCard] | None = None,
    rerank_result: RerankResult | None = None,
    rerank_method: str = "none",
    rerank_candidate_k: int = 0,
    semantic_method: str = "none",
    embedding_model: str | None = None,
    embedding_cache_path: str | None = None,
    embedding_cache_hit_count: int = 0,
    embedding_cache_miss_count: int = 0,
) -> MatchResult:
    items = []
    recommendations = []
    rule_rank_by_id = {
        card.mentor_id: idx
        for idx, card in enumerate(rule_candidate_cards or candidate_cards, start=1)
    }
    rerank_item_by_id = {
        item.mentor_id: item
        for item in (rerank_result.items if rerank_result else [])
    }
    for rank, card in enumerate(candidate_cards, start=1):
        rerank_item = rerank_item_by_id.get(card.mentor_id)
        display = MentorDisplayCard(
            rank=rank,
            is_recommended=rank <= top_k,
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
            industry_tags=card.industry_tags,
            position_tags=card.position_tags,
            company_tags=card.company_tags,
            raw_keywords=card.raw_keywords,
            summary=card.summary,
        )
        debug = MatchDebugInfo(
            final_score=card.final_score,
            relevance_score=card.score_breakdown.relevance_score,
            rule_rank=rule_rank_by_id.get(card.mentor_id),
            llm_rank=rerank_item.rank if rerank_item else None,
            llm_fit_score=rerank_item.llm_fit_score if rerank_item else None,
            score_breakdown=card.score_breakdown,
            matched_signals=card.matched_signals,
            industry_tags=card.industry_tags,
            position_tags=card.position_tags,
            company_tags=card.company_tags,
            raw_keywords=card.raw_keywords,
            possible_gap=possible_gap(card, profile),
            profile_parse_result=profile,
            rerank_note=rerank_item.rerank_note if rerank_item else None,
            recommendation_reason=build_reasons(card),
        )
        items.append(MatchItem(display=display, debug=debug))

        # Backward-compatible internal field. Product output should read
        # results[].display/debug instead of this legacy list.
        if rank <= top_k:
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
        top_k=top_k,
        total_mentors=total_mentors,
        candidate_count=len(candidate_cards),
        returned_count=min(top_k, len(candidate_cards)),
        used_rerank=used_rerank,
        semantic=MatchSemanticMetadata(
            enabled=semantic_method != "none",
            method=semantic_method,  # type: ignore[arg-type]
            embedding_model=embedding_model,
            cache_path=embedding_cache_path,
            cache_hit_count=embedding_cache_hit_count,
            cache_miss_count=embedding_cache_miss_count,
        ),
        rerank=MatchRerankMetadata(
            enabled=rerank_method == "llm",
            method=rerank_method,  # type: ignore[arg-type]
            candidate_k=rerank_candidate_k,
            success=bool(rerank_result.success) if rerank_result else False,
            fallback_used=bool(rerank_result.fallback_used) if rerank_result else False,
            latency_ms=rerank_result.latency_ms if rerank_result else None,
            error_message=rerank_result.error_message if rerank_result else None,
        ),
        results=items,
        recommendations=recommendations,
    )


def _join_values(values: list[str], limit: int = 4) -> str:
    return "、".join(values[:limit]) if values else "-"


def _display_industries(display: MentorDisplayCard) -> list[str]:
    if not display.industry_tags:
        return display.industries
    return [
        f"{item.tag} ({item.confidence:.2f})"
        for item in display.industry_tags
    ]


def _display_positions(display: MentorDisplayCard) -> list[str]:
    if not display.position_tags:
        return display.roles
    return [
        f"{item.tag} ({item.relation_type.value}, {item.confidence:.2f})"
        for item in display.position_tags
    ]


def _display_companies(display: MentorDisplayCard) -> list[str]:
    if not display.company_tags:
        return display.companies
    return [item.company_name for item in display.company_tags]


def format_markdown(result: MatchResult, *, show_score: bool = False) -> str:
    score_columns = " | final_score | company | role | skill | stage | industry | semantic" if show_score else ""
    score_header = " | ---: | ---: | ---: | ---: | ---: | ---: | ---:" if show_score else ""
    lines = [
        "| rank | mentor_id | 导师姓名 | 城市 | 职业年限 | 标准/相关行业 | 标准/相关公司 | 标准职位/关系 | 擅长方向 | 可辅导人群 | 简介"
        + score_columns
        + " |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---"
        + score_header
        + " |",
    ]
    for item in result.results[: result.top_k]:
        display = item.display
        breakdown = item.debug.score_breakdown
        semantic_cell = "-" if breakdown.semantic_match is None else f"{breakdown.semantic_match:.1f}"
        score_cell = (
            f" | {item.debug.final_score:.1f} | {breakdown.company_match:.1f} | "
            f"{breakdown.role_match:.1f} | {breakdown.skill_match:.1f} | "
            f"{breakdown.stage_match:.1f} | {breakdown.industry_match:.1f} | {semantic_cell}"
            if show_score
            else ""
        )
        lines.append(
            f"| {display.rank} | {display.mentor_id} | {display.name or '-'} | "
            f"{display.city or '-'} | {display.years_experience or '-'} | "
            f"{_join_values(_display_industries(display))} | "
            f"{_join_values(_display_companies(display))} | "
            f"{_join_values(_display_positions(display))} | "
            f"{_join_values(display.skills)} | "
            f"{_join_values(display.target_mentees)} | {display.summary or '-'}"
            f"{score_cell} |"
        )
    return "\n".join(lines)


def _row_values(values: list[str], limit: int = 4) -> str:
    return _join_values(values, limit=limit).replace("|", "/")


def format_rerank_report(
    *,
    query: str,
    result: MatchResult,
    rule_candidate_cards: list[MentorCandidateCard],
    final_cards: list[MentorCandidateCard],
    top_k: int,
    rerank_candidate_k: int,
    forbidden_removed: bool = False,
) -> str:
    lines = [
        "# LLM Rerank Test Report",
        "",
        "## Summary",
        f"- query: {query}",
        f"- top_k: {top_k}",
        f"- rerank_candidate_k: {rerank_candidate_k}",
        f"- llm_success: {result.rerank.success}",
        f"- fallback_used: {result.rerank.fallback_used}",
        f"- latency_ms: {result.rerank.latency_ms}",
        "",
        "## Student Input",
        query,
        "",
        "## Parsed Student Profile",
        "```json",
        result.student_profile.model_dump_json(ensure_ascii=False, indent=2),
        "```",
        "",
        "## Rule Ranking Before LLM Rerank: Top 30",
        "",
        "| rule_rank | mentor_id | name | rule_score | city | industries | companies | roles | skills | target_mentees | summary |",
        "|---:|---|---|---:|---|---|---|---|---|---|---|",
    ]
    for idx, card in enumerate(rule_candidate_cards[:rerank_candidate_k], start=1):
        lines.append(
            f"| {idx} | {card.mentor_id} | {card.name or '-'} | {card.final_score:.1f} | "
            f"{card.city or '-'} | {_row_values(card.industries)} | {_row_values(card.companies)} | "
            f"{_row_values(card.roles)} | {_row_values(card.skills)} | "
            f"{_row_values(card.target_mentees)} | {(card.summary or '-').replace('|', '/')} |"
        )

    final_id_to_card = {card.mentor_id: card for card in final_cards}
    lines.extend(
        [
            "",
            "## LLM Rerank Result: Top 10",
            "",
            "| llm_rank | original_rule_rank | mentor_id | name | llm_fit_score | rule_score | city | industries | companies | roles | skills | target_mentees |",
            "|---:|---:|---|---|---:|---:|---|---|---|---|---|---|",
        ]
    )
    for item in result.results[:top_k]:
        card = final_id_to_card.get(item.display.mentor_id)
        lines.append(
            f"| {item.debug.llm_rank or item.display.rank} | {item.debug.rule_rank or '-'} | "
            f"{item.display.mentor_id} | {item.display.name or '-'} | "
            f"{item.debug.llm_fit_score if item.debug.llm_fit_score is not None else '-'} | "
            f"{item.debug.final_score:.1f} | {item.display.city or '-'} | "
            f"{_row_values(card.industries if card else item.display.industries)} | "
            f"{_row_values(card.companies if card else item.display.companies)} | "
            f"{_row_values(card.roles if card else item.display.roles)} | "
            f"{_row_values(card.skills if card else item.display.skills)} | "
            f"{_row_values(card.target_mentees if card else item.display.target_mentees)} |"
        )

    lines.extend(["", "## Final Recommended Mentor Cards", ""])
    for item in result.results[:top_k]:
        display = item.display
        lines.extend(
            [
                f"### {display.rank}. {display.name or display.mentor_id}",
                f"- mentor_id: {display.mentor_id}",
                f"- city: {display.city or '-'}",
                f"- years_experience: {display.years_experience or '-'}",
                f"- industries: {_join_values(display.industries)}",
                f"- standard_industries: {_join_values(_display_industries(display))}",
                f"- companies: {_join_values(display.companies)}",
                f"- standard_companies: {_join_values(_display_companies(display))}",
                f"- roles: {_join_values(display.roles)}",
                f"- standard_positions: {_join_values(_display_positions(display))}",
                f"- raw_keywords: {_join_values(display.raw_keywords)}",
                f"- skills: {_join_values(display.skills)}",
                f"- target_mentees: {_join_values(display.target_mentees)}",
                f"- summary: {display.summary or '-'}",
                "",
            ]
        )

    changed = [
        item.display.mentor_id
        for item in result.results[:top_k]
        if item.debug.rule_rank is not None and item.debug.rule_rank != item.display.rank
    ]
    lines.extend(
        [
            "## Notes",
            f"- Did LLM change ordering significantly? {'yes' if changed else 'no'}",
            "- Any suspicious ranking? manual review recommended for low-score items",
            f"- Any forbidden wording found? {'removed from internal notes' if forbidden_removed else 'no'}",
            f"- Any fallback used? {result.rerank.fallback_used}",
            "",
        ]
    )
    return "\n".join(lines)


def _filters(result: MatchResult) -> dict[str, list[str]]:
    buckets = {
        "companies": [],
        "roles": [],
        "industries": [],
        "skills": [],
        "cities": [],
    }
    for item in result.results:
        display = item.display
        buckets["companies"].extend(display.companies)
        buckets["companies"].extend(
            item.company_name for item in display.company_tags
        )
        buckets["roles"].extend(display.roles)
        buckets["roles"].extend(item.tag for item in display.position_tags)
        buckets["industries"].extend(display.industries)
        buckets["industries"].extend(item.tag for item in display.industry_tags)
        buckets["skills"].extend(display.skills)
        if display.city:
            buckets["cities"].append(str(display.city))
    return {key: sorted(set(value for value in values if value)) for key, values in buckets.items()}


def _item_dict(item: MatchItem) -> dict:
    return {
        "display": item.display.model_dump(mode="json"),
        "debug": item.debug.model_dump(mode="json"),
    }


def to_product_dict(result: MatchResult) -> dict:
    recommended_ids = [item.display.mentor_id for item in result.results[: result.top_k]]
    semantic = result.semantic.model_dump(mode="json")
    return {
        "student_profile": result.student_profile.model_dump(mode="json"),
        "recommendation": {
            "top_k": result.top_k,
            "total_mentors": result.total_mentors,
            "recommended_mentor_ids": recommended_ids,
            "scoring_version": result.scoring_version,
            "semantic": {
                "enabled": semantic["enabled"],
                "method": semantic["method"],
                "embedding_model": semantic["embedding_model"],
                "cache_hit_count": semantic["cache_hit_count"],
                "cache_miss_count": semantic["cache_miss_count"],
            },
        },
        "semantic": result.semantic.model_dump(mode="json"),
        "rerank": result.rerank.model_dump(mode="json"),
        "all_mentors": [_item_dict(item) for item in result.results],
        "filters": _filters(result),
        "results": [_item_dict(item) for item in result.results],
    }


__all__ = ["build_match_result", "format_markdown", "format_rerank_report", "to_product_dict"]
