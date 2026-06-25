"""Rule-based mentor scoring with matched signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .aliases import AliasIndex, normalize_text
from .mentor_index import MentorDocument
from .schemas import (
    MatchedSignal,
    MatchedSignals,
    MentorCandidateCard,
    RuleScoreBreakdown,
    StudentProfile,
)


WEIGHTS = {
    "company_match": 0.30,
    "role_match": 0.20,
    "skill_or_help_match": 0.20,
    "target_mentee_match": 0.15,
    "industry_match": 0.10,
    "keyword_match": 0.05,
}


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _allow_substring(left: str, right: str) -> bool:
    shorter = min(len(left), len(right))
    return shorter >= 3 or (shorter >= 2 and _has_cjk(left) and _has_cjk(right))


@dataclass(frozen=True)
class FieldMatchConfig:
    category: str
    signal_field: str
    query_terms: list[str]
    structured_terms: list[str]
    fallback_terms: list[str]
    original_text: str


def _best_match_for_term(
    query_term: str,
    *,
    category: str,
    structured_terms: list[str],
    fallback_terms: list[str],
    original_text: str,
    aliases: AliasIndex,
) -> MatchedSignal | None:
    variants = aliases.variants(category, query_term)
    canonical = aliases.canonical_for(category, query_term)
    normalized_variants = [(variant, normalize_text(variant)) for variant in variants]

    structured = [(term, normalize_text(term)) for term in structured_terms]
    fallback = [(term, normalize_text(term)) for term in fallback_terms]
    raw = normalize_text(original_text)

    best: MatchedSignal | None = None

    def update(signal: MatchedSignal) -> None:
        nonlocal best
        if best is None or signal.weight > best.weight:
            best = signal

    for source_term, source_norm in structured:
        for variant, variant_norm in normalized_variants:
            if source_norm == variant_norm:
                update(
                    MatchedSignal(
                        query_term=query_term,
                        matched_term=source_term,
                        canonical=canonical,
                        source_field="structured",
                        match_type="exact" if normalize_text(query_term) == source_norm else "alias",
                        weight=1.0 if normalize_text(query_term) == source_norm else 0.9,
                    )
                )
            elif (
                variant_norm
                and _allow_substring(variant_norm, source_norm)
                and (variant_norm in source_norm or source_norm in variant_norm)
            ):
                update(
                    MatchedSignal(
                        query_term=query_term,
                        matched_term=source_term,
                        canonical=canonical,
                        source_field="structured",
                        match_type="substring",
                        weight=0.75,
                    )
                )

    for source_term, source_norm in fallback:
        for variant, variant_norm in normalized_variants:
            if variant_norm and _allow_substring(variant_norm, source_norm) and variant_norm in source_norm:
                update(
                    MatchedSignal(
                        query_term=query_term,
                        matched_term=source_term,
                        canonical=canonical,
                        source_field="summary_highlights_keywords",
                        match_type="substring",
                        weight=0.7,
                    )
                )

    for variant, variant_norm in normalized_variants:
        if variant_norm and _allow_substring(variant_norm, raw) and variant_norm in raw:
            update(
                MatchedSignal(
                    query_term=query_term,
                    matched_term=variant,
                    canonical=canonical,
                    source_field="raw_text",
                    match_type="raw_text",
                    weight=0.5,
                )
            )

    return best


def _score_category(config: FieldMatchConfig, aliases: AliasIndex) -> tuple[float, list[MatchedSignal]]:
    query_terms = [term for term in config.query_terms if str(term).strip()]
    if not query_terms:
        return 0.0, []
    signals = []
    total_weight = 0.0
    for query_term in query_terms:
        signal = _best_match_for_term(
            query_term,
            category=config.category,
            structured_terms=config.structured_terms,
            fallback_terms=config.fallback_terms,
            original_text=config.original_text,
            aliases=aliases,
        )
        if signal:
            signals.append(signal)
            total_weight += signal.weight
    return min(100.0, 100.0 * total_weight / len(query_terms)), signals


def _set_signal_field(matched: MatchedSignals, field: str, signals: list[MatchedSignal]) -> None:
    setattr(matched, field, signals)


def _merge_signals(*groups: list[MatchedSignal]) -> list[MatchedSignal]:
    seen = set()
    merged = []
    for group in groups:
        for signal in group:
            key = (signal.query_term, signal.matched_term, signal.source_field, signal.match_type)
            if key not in seen:
                seen.add(key)
                merged.append(signal)
    return merged


def _weighted_category_total(scores: dict[str, float], active_weights: dict[str, float]) -> float:
    if not active_weights:
        return 0.0
    weighted_total = sum(scores[name] * weight for name, weight in active_weights.items())
    return weighted_total / sum(active_weights.values())


def _reason_from_signal(label: str, signals: list[MatchedSignal]) -> str | None:
    if not signals:
        return None
    terms = []
    for signal in signals[:3]:
        terms.append(signal.canonical or signal.matched_term)
    return f"{label}匹配：" + "、".join(dict.fromkeys(terms))


def build_reasons(card: MentorCandidateCard) -> list[str]:
    reasons = []
    signal_map = [
        ("目标公司/机构", card.matched_signals.companies),
        ("岗位方向", card.matched_signals.roles),
        ("辅导需求", card.matched_signals.skills),
        ("学员阶段", card.matched_signals.target_mentees),
        ("行业方向", card.matched_signals.industries),
        ("关键词", card.matched_signals.keywords),
    ]
    for label, signals in signal_map:
        reason = _reason_from_signal(label, signals)
        if reason:
            if label == "目标公司/机构":
                reason = reason.replace("匹配：", "相关信号：")
            reasons.append(reason)
        if len(reasons) >= 4:
            break
    return reasons or ["导师资料与学员需求存在关键词相关性。"]


def possible_gap(card: MentorCandidateCard, profile: StudentProfile) -> str | None:
    if profile.target_roles and not card.matched_signals.roles:
        return "岗位方向匹配较弱，建议人工确认导师是否熟悉该目标岗位。"
    if profile.target_companies and not card.matched_signals.companies:
        return "目标公司/机构信号较弱，推荐主要来自行业或技能匹配。"
    return None


def score_mentor(
    document: MentorDocument,
    profile: StudentProfile,
    aliases: AliasIndex,
) -> MentorCandidateCard:
    result = document.result
    extraction = result.extraction
    fallback_terms = [
        *(extraction.keywords or []),
        *(extraction.highlights or []),
        extraction.summary or "",
    ]
    original = result.original_fields
    matched = MatchedSignals()

    category_configs = {
        "company_match": FieldMatchConfig(
            category="companies",
            signal_field="companies",
            query_terms=profile.target_companies,
            structured_terms=extraction.companies,
            fallback_terms=fallback_terms,
            original_text=document.original_text,
        ),
        "role_match": FieldMatchConfig(
            category="roles",
            signal_field="roles",
            query_terms=profile.target_roles,
            structured_terms=extraction.roles,
            fallback_terms=fallback_terms,
            original_text=document.original_text,
        ),
        "skill_or_help_match": FieldMatchConfig(
            category="skills",
            signal_field="skills",
            query_terms=profile.needed_help,
            structured_terms=extraction.skills,
            fallback_terms=fallback_terms,
            original_text=document.original_text,
        ),
        "target_mentee_match": FieldMatchConfig(
            category="stages",
            signal_field="target_mentees",
            query_terms=profile.current_stage,
            structured_terms=[*extraction.target_mentees, str(original.coachable_levels or "")],
            fallback_terms=fallback_terms,
            original_text=document.original_text,
        ),
        "industry_match": FieldMatchConfig(
            category="industries",
            signal_field="industries",
            query_terms=profile.target_industries,
            structured_terms=[*extraction.industries, str(original.industry_tags or "")],
            fallback_terms=fallback_terms,
            original_text=document.original_text,
        ),
        "keyword_match": FieldMatchConfig(
            category="skills",
            signal_field="keywords",
            query_terms=profile.keywords[:10],
            structured_terms=[
                *extraction.keywords,
                *extraction.skills,
                *extraction.roles,
                *extraction.companies,
                *extraction.industries,
            ],
            fallback_terms=fallback_terms,
            original_text=document.search_text,
        ),
    }

    scores: dict[str, float] = {}
    structured_scores: dict[str, float] = {}
    raw_text_scores: dict[str, float] = {}
    for score_name, config in category_configs.items():
        structured_config = FieldMatchConfig(
            category=config.category,
            signal_field=config.signal_field,
            query_terms=config.query_terms,
            structured_terms=config.structured_terms,
            fallback_terms=[],
            original_text="",
        )
        raw_text_config = FieldMatchConfig(
            category=config.category,
            signal_field=config.signal_field,
            query_terms=config.query_terms,
            structured_terms=[],
            fallback_terms=config.fallback_terms,
            original_text=config.original_text,
        )
        structured_score, structured_signals = _score_category(structured_config, aliases)
        raw_text_score, raw_text_signals = _score_category(raw_text_config, aliases)
        structured_scores[score_name] = structured_score
        raw_text_scores[score_name] = raw_text_score
        scores[score_name] = max(structured_score, raw_text_score)
        _set_signal_field(matched, config.signal_field, _merge_signals(structured_signals, raw_text_signals))

    active_weights = {
        name: weight
        for name, weight in WEIGHTS.items()
        if category_configs[name].query_terms
    }
    structured_total = _weighted_category_total(structured_scores, active_weights)
    raw_text_total = _weighted_category_total(raw_text_scores, active_weights)
    semantic_score = None
    component_weights = {"structured": 0.50, "raw_text": 0.30}
    if semantic_score is not None:
        component_weights["semantic"] = 0.20
    total_weight = sum(component_weights.values())
    total = (
        structured_total * component_weights["structured"]
        + raw_text_total * component_weights["raw_text"]
    )
    if semantic_score is not None:
        total += semantic_score * component_weights["semantic"]
    total = round(min(100.0, total / total_weight), 2) if total_weight else 0.0
    breakdown = RuleScoreBreakdown(
        company_match=round(scores["company_match"], 2),
        role_match=round(scores["role_match"], 2),
        skill_or_help_match=round(scores["skill_or_help_match"], 2),
        target_mentee_match=round(scores["target_mentee_match"], 2),
        industry_match=round(scores["industry_match"], 2),
        keyword_match=round(scores["keyword_match"], 2),
        structured_score=round(structured_total, 2),
        raw_text_score=round(raw_text_total, 2),
        semantic_score=semantic_score,
        final_score=total,
        total=total,
    )
    return MentorCandidateCard(
        mentor_id=result.mentor_id,
        name=result.original_fields.mentor_name,
        gender=result.original_fields.gender,
        city=result.original_fields.city,
        years_experience=result.original_fields.career_years,
        industries=extraction.industries,
        companies=extraction.companies,
        roles=extraction.roles,
        skills=extraction.skills,
        credentials=extraction.credentials,
        education=extraction.education,
        target_mentees=extraction.target_mentees,
        highlights=extraction.highlights,
        keywords=extraction.keywords,
        summary=extraction.summary,
        matched_signals=matched,
        rule_score=total,
        structured_score=round(structured_total, 2),
        raw_text_score=round(raw_text_total, 2),
        semantic_score=semantic_score,
        final_score=total,
        score_breakdown=breakdown,
    )


def rank_candidates(
    documents: Iterable[MentorDocument],
    profile: StudentProfile,
    aliases: AliasIndex,
    *,
    candidate_pool_size: int = 30,
) -> list[MentorCandidateCard]:
    cards = [score_mentor(document, profile, aliases) for document in documents]
    cards.sort(
        key=lambda card: (
            card.rule_score,
            card.structured_score,
            card.raw_text_score,
            len(card.matched_signals.companies),
            len(card.matched_signals.skills),
            len(card.matched_signals.target_mentees),
        ),
        reverse=True,
    )
    return cards[:candidate_pool_size]


__all__ = [
    "WEIGHTS",
    "build_reasons",
    "possible_gap",
    "rank_candidates",
    "score_mentor",
]
