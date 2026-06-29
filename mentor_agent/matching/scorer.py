"""Rule-based mentor scoring with matched signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Iterable

from .aliases import AliasIndex, normalize_text
from .embeddings import EmbeddingCache, cosine_similarity, get_embedding
from .mentor_index import MentorDocument
from .schemas import (
    MatchedSignal,
    MatchedSignals,
    MentorCandidateCard,
    RuleScoreBreakdown,
    StudentProfile,
)


WEIGHTS = {
    "company_match": 0.25,
    "role_match": 0.20,
    "skill_or_help_match": 0.20,
    "industry_match": 0.10,
    "target_mentee_match": 0.10,
    "years_match": 0.05,
    "semantic_match": 0.10,
}

MENTOR_QUALITY_FACTOR = 1.0
AVAILABILITY_FACTOR = 1.0
ROLE_SEMANTIC_RAW_MIN = 0.50
HELP_SEMANTIC_RAW_MIN = 0.45
SCOPED_SEMANTIC_PERCENTILE_MIN = 60.0
STANDARD_TAG_CONFIDENCE_MIN = 0.70


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
    structured_source_field: str = "structured"
    fallback_source_field: str = "summary_highlights_keywords"
    structured_exact_weight: float = 1.0
    structured_alias_weight: float = 0.9
    structured_substring_weight: float = 0.75
    fallback_weight: float = 0.7
    raw_text_weight: float = 0.5


@dataclass
class SemanticContext:
    method: str = "none"
    embedding_model: str = "fake-hash-v1"
    cache: EmbeddingCache | None = None
    query_embedding: list[float] | None = None
    role_query_embedding: list[float] | None = None
    help_query_embedding: list[float] | None = None
    global_query_embedding: list[float] | None = None
    scoped_scores_by_mentor_id: dict[str, "ScopedSemanticScores"] = field(default_factory=dict)


@dataclass
class ScopedSemanticScores:
    role_raw_cosine: float | None = None
    role_percentile: float | None = None
    help_raw_cosine: float | None = None
    help_percentile: float | None = None
    global_raw_cosine: float | None = None
    global_percentile: float | None = None


def _best_match_for_term(
    query_term: str,
    *,
    category: str,
    structured_terms: list[str],
    fallback_terms: list[str],
    original_text: str,
    aliases: AliasIndex,
    structured_source_field: str = "structured",
    fallback_source_field: str = "summary_highlights_keywords",
    structured_exact_weight: float = 1.0,
    structured_alias_weight: float = 0.9,
    structured_substring_weight: float = 0.75,
    fallback_weight: float = 0.7,
    raw_text_weight: float = 0.5,
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
                        source_field=structured_source_field,
                        match_type="exact" if normalize_text(query_term) == source_norm else "alias",
                        weight=(
                            structured_exact_weight
                            if normalize_text(query_term) == source_norm
                            else structured_alias_weight
                        ),
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
                        source_field=structured_source_field,
                        match_type="substring",
                        weight=structured_substring_weight,
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
                        source_field=fallback_source_field,
                        match_type="substring",
                        weight=fallback_weight,
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
                    weight=raw_text_weight,
                )
            )

    return best


def _score_config_group(
    configs: list[FieldMatchConfig],
    aliases: AliasIndex,
) -> tuple[float, list[MatchedSignal]]:
    if not configs:
        return 0.0, []
    query_terms = [term for term in configs[0].query_terms if str(term).strip()]
    if not query_terms:
        return 0.0, []
    signals: list[MatchedSignal] = []
    total_weight = 0.0
    for query_term in query_terms:
        best: MatchedSignal | None = None
        for config in configs:
            signal = _best_match_for_term(
                query_term,
                category=config.category,
                structured_terms=config.structured_terms,
                fallback_terms=config.fallback_terms,
                original_text=config.original_text,
                aliases=aliases,
                structured_source_field=config.structured_source_field,
                fallback_source_field=config.fallback_source_field,
                structured_exact_weight=config.structured_exact_weight,
                structured_alias_weight=config.structured_alias_weight,
                structured_substring_weight=config.structured_substring_weight,
                fallback_weight=config.fallback_weight,
                raw_text_weight=config.raw_text_weight,
            )
            if signal and (best is None or signal.weight > best.weight):
                best = signal
        if best:
            signals.append(best)
            total_weight += best.weight
    return min(100.0, 100.0 * total_weight / len(query_terms)), signals


def _set_signal_field(matched: MatchedSignals, field: str, signals: list[MatchedSignal]) -> None:
    setattr(matched, field, signals)


def _merge_signals(*groups: list[MatchedSignal]) -> list[MatchedSignal]:
    seen = set()
    merged = []
    for group in groups:
        for signal in group:
            key = (
                signal.query_term,
                signal.matched_term,
                signal.source_field,
                signal.match_type,
            )
            if key not in seen:
                seen.add(key)
                merged.append(signal)
    return merged


def _weighted_category_total(scores: dict[str, float], active_weights: dict[str, float]) -> float:
    if not active_weights:
        return 0.0
    weighted_total = sum(scores[name] * weight for name, weight in active_weights.items())
    return weighted_total / sum(active_weights.values())


def build_student_search_text(profile: StudentProfile) -> str:
    parts = [
        profile.raw_query,
        *profile.target_industries,
        *profile.target_companies,
        *profile.target_roles,
        *profile.current_stage,
        *profile.needed_help,
        *profile.preferred_background,
        *profile.keywords,
    ]
    return " ".join(str(part) for part in parts if part)


def build_role_student_text(profile: StudentProfile) -> str:
    parts = [*profile.target_roles, *profile.keywords, profile.raw_query]
    return " ".join(str(part) for part in parts if part)


def build_help_student_text(profile: StudentProfile) -> str:
    parts = [*profile.needed_help, *profile.preferred_background, *profile.keywords]
    return " ".join(str(part) for part in parts if part)


def _provider_method(method: str) -> str:
    return "local" if method == "local-scoped-bonus" else method


def _mentor_role_text(document: MentorDocument) -> str:
    extraction = document.result.extraction
    parts = [
        *(item.tag for item in extraction.position_tags),
        *(
            keyword
            for item in extraction.position_tags
            for keyword in item.raw_keywords
        ),
        *extraction.roles,
        *extraction.raw_keywords,
        *extraction.keywords,
        *extraction.highlights,
        extraction.summary or "",
    ]
    return " ".join(str(part) for part in parts if part)


def _mentor_help_text(document: MentorDocument) -> str:
    extraction = document.result.extraction
    parts = [
        *extraction.skills,
        *extraction.target_mentees,
        *extraction.highlights,
        extraction.summary or "",
    ]
    return " ".join(str(part) for part in parts if part)


def _role_text_quality(document: MentorDocument) -> str:
    extraction = document.result.extraction
    if extraction.roles or any(
        item.confidence >= STANDARD_TAG_CONFIDENCE_MIN
        for item in extraction.position_tags
    ):
        return "strong"
    if (
        extraction.position_tags
        or extraction.raw_keywords
        or extraction.keywords
        or extraction.highlights
        or extraction.summary
    ):
        return "weak"
    return "none"


def _cached_embedding(
    document: MentorDocument,
    *,
    text: str,
    context: SemanticContext,
    model_suffix: str = "",
) -> list[float]:
    result = document.result
    model_key = f"{context.embedding_model}{model_suffix}"
    embedding = context.cache.get(result.mentor_id, result.record_hash, model_key) if context.cache else None
    if embedding is None:
        embedding = get_embedding(
            text,
            method=_provider_method(context.method),
            embedding_model=context.embedding_model,
        )
        if context.cache:
            context.cache.set(result.mentor_id, result.record_hash, model_key, embedding)
    return embedding


def _percentiles(raw_scores: dict[str, float | None]) -> dict[str, float | None]:
    valid = [(mentor_id, score) for mentor_id, score in raw_scores.items() if score is not None]
    if not valid:
        return {mentor_id: None for mentor_id in raw_scores}
    if len(valid) == 1:
        return {mentor_id: 100.0 for mentor_id in raw_scores}
    sorted_scores = sorted(valid, key=lambda item: item[1])
    ranks: dict[str, float] = {}
    index = 0
    last_index = len(sorted_scores) - 1
    while index < len(sorted_scores):
        end = index
        while end + 1 < len(sorted_scores) and sorted_scores[end + 1][1] == sorted_scores[index][1]:
            end += 1
        average_rank = (index + end) / 2.0
        percentile = round(100.0 * average_rank / last_index, 2)
        for mentor_id, _ in sorted_scores[index : end + 1]:
            ranks[mentor_id] = percentile
        index = end + 1
    return {mentor_id: ranks.get(mentor_id) for mentor_id in raw_scores}


def _prepare_scoped_semantic_scores(
    documents: list[MentorDocument],
    profile: StudentProfile,
    context: SemanticContext,
) -> None:
    if context.method != "local-scoped-bonus":
        return
    role_raw: dict[str, float | None] = {}
    help_raw: dict[str, float | None] = {}
    global_raw: dict[str, float | None] = {}
    for document in documents:
        mentor_id = document.result.mentor_id
        if context.role_query_embedding is not None:
            role_raw[mentor_id] = cosine_similarity(
                context.role_query_embedding,
                _cached_embedding(document, text=_mentor_role_text(document), context=context, model_suffix=":role"),
            )
        else:
            role_raw[mentor_id] = None
        if context.help_query_embedding is not None:
            help_raw[mentor_id] = cosine_similarity(
                context.help_query_embedding,
                _cached_embedding(document, text=_mentor_help_text(document), context=context, model_suffix=":help"),
            )
        else:
            help_raw[mentor_id] = None
        if context.global_query_embedding is not None:
            global_raw[mentor_id] = cosine_similarity(
                context.global_query_embedding,
                _cached_embedding(document, text=document.mentor_search_text, context=context, model_suffix=":global"),
            )
        else:
            global_raw[mentor_id] = None

    role_percentiles = _percentiles(role_raw)
    help_percentiles = _percentiles(help_raw)
    global_percentiles = _percentiles(global_raw)
    context.scoped_scores_by_mentor_id = {
        document.result.mentor_id: ScopedSemanticScores(
            role_raw_cosine=role_raw.get(document.result.mentor_id),
            role_percentile=role_percentiles.get(document.result.mentor_id),
            help_raw_cosine=help_raw.get(document.result.mentor_id),
            help_percentile=help_percentiles.get(document.result.mentor_id),
            global_raw_cosine=global_raw.get(document.result.mentor_id),
            global_percentile=global_percentiles.get(document.result.mentor_id),
        )
        for document in documents
    }


def _semantic_score(document: MentorDocument, context: SemanticContext | None) -> float | None:
    if not context or context.method == "none" or context.query_embedding is None:
        return None
    result = document.result
    embedding = context.cache.get(result.mentor_id, result.record_hash, context.embedding_model) if context.cache else None
    if embedding is None:
        embedding = get_embedding(
            document.mentor_search_text,
            method=_provider_method(context.method),
            embedding_model=context.embedding_model,
        )
        if context.cache:
            context.cache.set(result.mentor_id, result.record_hash, context.embedding_model, embedding)
    similarity = cosine_similarity(context.query_embedding, embedding)
    return round(max(0.0, min(100.0, (similarity + 1.0) * 50.0)), 2)


def _score_from_cosine(raw_cosine: float | None) -> float | None:
    if raw_cosine is None:
        return None
    return round(max(0.0, min(100.0, (raw_cosine + 1.0) * 50.0)), 2)


def _role_semantic_bonus(
    *,
    profile: StudentProfile,
    rule_role_match: float,
    scoped: ScopedSemanticScores | None,
    text_quality: str,
) -> float:
    if not profile.target_roles or not scoped or scoped.role_percentile is None:
        return 0.0
    if scoped.role_raw_cosine is None or scoped.role_raw_cosine < ROLE_SEMANTIC_RAW_MIN:
        return 0.0
    if scoped.role_percentile < SCOPED_SEMANTIC_PERCENTILE_MIN:
        return 0.0
    if rule_role_match > 0:
        cap, weight = 15.0, 0.20
    elif text_quality == "strong":
        cap, weight = 35.0, 0.35
    elif text_quality == "weak":
        cap, weight = 22.0, 0.25
    else:
        return 0.0
    return round(min(cap, weight * scoped.role_percentile), 2)


def _help_semantic_bonus(
    *,
    profile: StudentProfile,
    rule_skill_match: float,
    scoped: ScopedSemanticScores | None,
) -> float:
    if not (profile.needed_help or profile.preferred_background) or not scoped or scoped.help_percentile is None:
        return 0.0
    if scoped.help_raw_cosine is None or scoped.help_raw_cosine < HELP_SEMANTIC_RAW_MIN:
        return 0.0
    if scoped.help_percentile < SCOPED_SEMANTIC_PERCENTILE_MIN:
        return 0.0
    if rule_skill_match > 0:
        cap, weight = 20.0, 0.25
    else:
        cap, weight = 35.0, 0.35
    return round(min(cap, weight * scoped.help_percentile), 2)


def _parse_years(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    digits = "".join(char for char in str(value) if char.isdigit() or char == ".")
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _years_match(student_work_years: int | None, mentor_years: object, document: MentorDocument) -> float:
    if student_work_years is None:
        return 0.0
    years = _parse_years(mentor_years)
    text = normalize_text(document.search_text)
    senior_signal = any(term in text for term in ("管理", "负责人", "总监", "专家", "leader", "head"))
    if student_work_years <= 1:
        return 70.0
    if student_work_years <= 5:
        if years is None:
            return 60.0
        return 100.0 if years >= 5 else max(40.0, years / 5 * 100)
    if years is None:
        return 75.0 if senior_signal else 55.0
    if years >= 8 or senior_signal:
        return 100.0
    return max(40.0, years / 8 * 100)


def _weighted_relevance(scores: dict[str, float | None], active_terms: dict[str, bool]) -> float:
    active: dict[str, float] = {}
    for name, weight in WEIGHTS.items():
        value = scores.get(name)
        if value is None:
            continue
        if name == "semantic_match":
            active[name] = weight
        elif active_terms.get(name):
            active[name] = weight
    if not active:
        return 0.0
    total = sum(float(scores[name] or 0.0) * weight for name, weight in active.items())
    return round(min(100.0, total / sum(active.values())), 2)


def _final_score(relevance_score: float) -> float:
    total = relevance_score * AVAILABILITY_FACTOR * MENTOR_QUALITY_FACTOR
    return round(min(100.0, total), 2)


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
    semantic_context: SemanticContext | None = None,
) -> MentorCandidateCard:
    result = document.result
    extraction = result.extraction
    fallback_terms = [
        *(extraction.keywords or []),
        *(extraction.highlights or []),
        extraction.summary or "",
    ]
    high_industry_tags = [
        item.tag
        for item in extraction.industry_tags
        if item.confidence >= STANDARD_TAG_CONFIDENCE_MIN
    ]
    low_industry_tags = [
        item.tag
        for item in extraction.industry_tags
        if item.confidence < STANDARD_TAG_CONFIDENCE_MIN
    ]
    high_position_tags = [
        item.tag
        for item in extraction.position_tags
        if item.confidence >= STANDARD_TAG_CONFIDENCE_MIN
    ]
    low_position_tags = [
        item.tag
        for item in extraction.position_tags
        if item.confidence < STANDARD_TAG_CONFIDENCE_MIN
    ]
    position_raw_keywords = [
        keyword
        for item in extraction.position_tags
        for keyword in item.raw_keywords
    ]
    high_company_names = [
        item.company_name
        for item in extraction.company_tags
        if item.confidence >= STANDARD_TAG_CONFIDENCE_MIN
    ]
    low_company_names = [
        item.company_name
        for item in extraction.company_tags
        if item.confidence < STANDARD_TAG_CONFIDENCE_MIN
    ]
    company_types = [
        item.company_type
        for item in extraction.company_tags
        if item.company_type
    ]
    has_standard_matching_data = bool(
        extraction.industry_tags
        or extraction.position_tags
        or extraction.company_tags
        or extraction.raw_keywords
    )
    legacy_source_fields = {
        "company_match": "companies",
        "role_match": "roles",
        "skill_or_help_match": "skills",
        "target_mentee_match": "target_mentees",
        "industry_match": "industries",
        "keyword_match": "legacy_keywords",
        "background_match": "legacy_background",
    }
    if not has_standard_matching_data:
        legacy_source_fields = {
            score_name: "structured"
            for score_name in legacy_source_fields
        }
    original = result.original_fields
    matched = MatchedSignals()

    query_terms_by_score = {
        "company_match": profile.target_companies,
        "role_match": profile.target_roles,
        "skill_or_help_match": profile.needed_help,
        "target_mentee_match": profile.current_stage,
        "industry_match": profile.target_industries,
        "keyword_match": profile.keywords[:10],
        "background_match": profile.preferred_background,
    }

    legacy_configs = {
        "company_match": FieldMatchConfig(
            category="companies",
            signal_field="companies",
            query_terms=profile.target_companies,
            structured_terms=extraction.companies,
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["company_match"],
        ),
        "role_match": FieldMatchConfig(
            category="roles",
            signal_field="roles",
            query_terms=profile.target_roles,
            structured_terms=extraction.roles,
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["role_match"],
        ),
        "skill_or_help_match": FieldMatchConfig(
            category="skills",
            signal_field="skills",
            query_terms=profile.needed_help,
            structured_terms=extraction.skills,
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["skill_or_help_match"],
        ),
        "target_mentee_match": FieldMatchConfig(
            category="stages",
            signal_field="target_mentees",
            query_terms=profile.current_stage,
            structured_terms=[*extraction.target_mentees, str(original.coachable_levels or "")],
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["target_mentee_match"],
        ),
        "industry_match": FieldMatchConfig(
            category="industries",
            signal_field="industries",
            query_terms=profile.target_industries,
            structured_terms=[*extraction.industries, str(original.industry_tags or "")],
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["industry_match"],
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
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["keyword_match"],
        ),
        "background_match": FieldMatchConfig(
            category="skills",
            signal_field="keywords",
            query_terms=profile.preferred_background,
            structured_terms=[
                *extraction.keywords,
                *extraction.skills,
                *extraction.roles,
                *extraction.companies,
                *extraction.industries,
                *(extraction.highlights or []),
            ],
            fallback_terms=[],
            original_text="",
            structured_source_field=legacy_source_fields["background_match"],
        ),
    }

    standard_configs = {
        "company_match": [
            FieldMatchConfig(
                category="companies",
                signal_field="companies",
                query_terms=profile.target_companies,
                structured_terms=high_company_names,
                fallback_terms=[],
                original_text="",
                structured_source_field="company_tags.company_name",
            )
        ],
        "role_match": [
            FieldMatchConfig(
                category="roles",
                signal_field="roles",
                query_terms=profile.target_roles,
                structured_terms=high_position_tags,
                fallback_terms=[],
                original_text="",
                structured_source_field="position_tags.tag",
            )
        ],
        "industry_match": [
            FieldMatchConfig(
                category="industries",
                signal_field="industries",
                query_terms=profile.target_industries,
                structured_terms=high_industry_tags,
                fallback_terms=[],
                original_text="",
                structured_source_field="industry_tags.tag",
            )
        ],
    }

    weak_configs = {
        "company_match": [
            FieldMatchConfig(
                category="companies",
                signal_field="companies",
                query_terms=profile.target_companies,
                structured_terms=low_company_names,
                fallback_terms=[],
                original_text="",
                structured_source_field="company_tags.company_name",
                structured_exact_weight=0.65,
                structured_alias_weight=0.60,
                structured_substring_weight=0.50,
            ),
            FieldMatchConfig(
                category="companies",
                signal_field="companies",
                query_terms=profile.target_companies,
                structured_terms=company_types,
                fallback_terms=[],
                original_text="",
                structured_source_field="company_tags.company_type",
                structured_exact_weight=0.55,
                structured_alias_weight=0.50,
                structured_substring_weight=0.45,
            ),
        ],
        "role_match": [
            FieldMatchConfig(
                category="roles",
                signal_field="roles",
                query_terms=profile.target_roles,
                structured_terms=low_position_tags,
                fallback_terms=[],
                original_text="",
                structured_source_field="position_tags.tag",
                structured_exact_weight=0.65,
                structured_alias_weight=0.60,
                structured_substring_weight=0.50,
            ),
            FieldMatchConfig(
                category="roles",
                signal_field="roles",
                query_terms=profile.target_roles,
                structured_terms=[
                    *position_raw_keywords,
                    *extraction.raw_keywords,
                ],
                fallback_terms=[],
                original_text="",
                structured_source_field="raw_keywords",
                structured_exact_weight=0.60,
                structured_alias_weight=0.55,
                structured_substring_weight=0.45,
            ),
        ],
        "industry_match": [
            FieldMatchConfig(
                category="industries",
                signal_field="industries",
                query_terms=profile.target_industries,
                structured_terms=low_industry_tags,
                fallback_terms=[],
                original_text="",
                structured_source_field="industry_tags.tag",
                structured_exact_weight=0.65,
                structured_alias_weight=0.60,
                structured_substring_weight=0.50,
            )
        ],
        "keyword_match": [
            FieldMatchConfig(
                category="skills",
                signal_field="keywords",
                query_terms=profile.keywords[:10],
                structured_terms=[
                    *position_raw_keywords,
                    *extraction.raw_keywords,
                ],
                fallback_terms=[],
                original_text="",
                structured_source_field="raw_keywords",
                structured_exact_weight=0.60,
                structured_alias_weight=0.55,
                structured_substring_weight=0.45,
            )
        ],
        "background_match": [
            FieldMatchConfig(
                category="skills",
                signal_field="keywords",
                query_terms=profile.preferred_background,
                structured_terms=[
                    *position_raw_keywords,
                    *extraction.raw_keywords,
                ],
                fallback_terms=[],
                original_text="",
                structured_source_field="raw_keywords",
                structured_exact_weight=0.60,
                structured_alias_weight=0.55,
                structured_substring_weight=0.45,
            )
        ],
    }

    scores: dict[str, float] = {}
    structured_scores: dict[str, float] = {}
    raw_text_scores: dict[str, float] = {}
    for score_name, legacy_config in legacy_configs.items():
        structured_group = [
            *standard_configs.get(score_name, []),
            legacy_config,
        ]
        raw_text_config = FieldMatchConfig(
            category=legacy_config.category,
            signal_field=legacy_config.signal_field,
            query_terms=legacy_config.query_terms,
            structured_terms=[],
            fallback_terms=fallback_terms,
            original_text=(
                document.search_text
                if score_name in {"keyword_match", "background_match"}
                else document.original_text
            ),
        )
        raw_group = [
            *weak_configs.get(score_name, []),
            raw_text_config,
        ]
        structured_score, structured_signals = _score_config_group(
            structured_group,
            aliases,
        )
        raw_text_score, raw_text_signals = _score_config_group(
            raw_group,
            aliases,
        )
        if has_standard_matching_data:
            final_score, final_signals = _score_config_group(
                [*structured_group, *raw_group],
                aliases,
            )
        else:
            final_score = max(structured_score, raw_text_score)
            final_signals = _merge_signals(
                structured_signals,
                raw_text_signals,
            )
        structured_scores[score_name] = structured_score
        raw_text_scores[score_name] = raw_text_score
        scores[score_name] = final_score
        _set_signal_field(
            matched,
            legacy_config.signal_field,
            final_signals,
        )

    category_weights = {
        "company_match": WEIGHTS["company_match"],
        "role_match": WEIGHTS["role_match"],
        "skill_or_help_match": WEIGHTS["skill_or_help_match"],
        "target_mentee_match": WEIGHTS["target_mentee_match"],
        "industry_match": WEIGHTS["industry_match"],
        "keyword_match": 0.05,
        "background_match": 0.05,
    }
    active_weights = {
        name: weight
        for name, weight in category_weights.items()
        if query_terms_by_score[name]
    }
    structured_total = _weighted_category_total(structured_scores, active_weights)
    raw_text_total = _weighted_category_total(raw_text_scores, active_weights)
    scoped_semantic = (
        semantic_context.scoped_scores_by_mentor_id.get(result.mentor_id)
        if semantic_context and semantic_context.method == "local-scoped-bonus"
        else None
    )
    semantic_score = (
        _score_from_cosine(scoped_semantic.global_raw_cosine)
        if scoped_semantic
        else _semantic_score(document, semantic_context)
    )
    rule_role_match = scores["role_match"]
    rule_skill_match = scores["skill_or_help_match"]
    role_bonus = _role_semantic_bonus(
        profile=profile,
        rule_role_match=rule_role_match,
        scoped=scoped_semantic,
        text_quality=_role_text_quality(document),
    )
    help_bonus = _help_semantic_bonus(
        profile=profile,
        rule_skill_match=rule_skill_match,
        scoped=scoped_semantic,
    )
    role_match_final = min(100.0, rule_role_match + role_bonus)
    skill_match_final = min(100.0, rule_skill_match + help_bonus)
    effective_semantic_score = None if scoped_semantic else semantic_score
    years_score = _years_match(profile.work_years, result.original_fields.career_years, document)
    score_inputs: dict[str, float | None] = {
        "company_match": scores["company_match"],
        "role_match": role_match_final,
        "skill_or_help_match": skill_match_final,
        "industry_match": scores["industry_match"],
        "target_mentee_match": scores["target_mentee_match"],
        "years_match": years_score,
        "semantic_match": effective_semantic_score,
    }
    active_terms = {
        "company_match": bool(profile.target_companies),
        "role_match": bool(profile.target_roles),
        "skill_or_help_match": bool(profile.needed_help or (scoped_semantic and profile.preferred_background)),
        "industry_match": bool(profile.target_industries),
        "target_mentee_match": bool(profile.current_stage),
        "years_match": profile.work_years is not None,
    }
    relevance_score = _weighted_relevance(score_inputs, active_terms)
    total = _final_score(relevance_score)
    breakdown = RuleScoreBreakdown(
        company_match=round(scores["company_match"], 2),
        role_match=round(role_match_final, 2),
        skill_match=round(skill_match_final, 2),
        skill_or_help_match=round(skill_match_final, 2),
        stage_match=round(scores["target_mentee_match"], 2),
        target_mentee_match=round(scores["target_mentee_match"], 2),
        years_match=round(years_score, 2),
        background_match=round(scores["background_match"], 2),
        industry_match=round(scores["industry_match"], 2),
        keyword_match=round(scores["keyword_match"], 2),
        raw_text_match=round(raw_text_total, 2),
        semantic_match=semantic_score,
        rule_role_match=round(rule_role_match, 2) if scoped_semantic else None,
        role_semantic_raw_cosine=round(scoped_semantic.role_raw_cosine, 4)
        if scoped_semantic and scoped_semantic.role_raw_cosine is not None
        else None,
        role_semantic_percentile=round(scoped_semantic.role_percentile, 2)
        if scoped_semantic and scoped_semantic.role_percentile is not None
        else None,
        role_semantic_bonus=role_bonus if scoped_semantic else None,
        role_match_final=round(role_match_final, 2) if scoped_semantic else None,
        rule_skill_match=round(rule_skill_match, 2) if scoped_semantic else None,
        help_semantic_raw_cosine=round(scoped_semantic.help_raw_cosine, 4)
        if scoped_semantic and scoped_semantic.help_raw_cosine is not None
        else None,
        help_semantic_percentile=round(scoped_semantic.help_percentile, 2)
        if scoped_semantic and scoped_semantic.help_percentile is not None
        else None,
        help_semantic_bonus=help_bonus if scoped_semantic else None,
        skill_match_final=round(skill_match_final, 2) if scoped_semantic else None,
        global_semantic_score=semantic_score if scoped_semantic else None,
        semantic_fusion_mode="scoped_bonus" if scoped_semantic else None,
        structured_score=round(structured_total, 2),
        raw_text_score=round(raw_text_total, 2),
        semantic_score=semantic_score,
        relevance_score=relevance_score,
        availability_factor=AVAILABILITY_FACTOR,
        mentor_quality_factor=MENTOR_QUALITY_FACTOR,
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
        industry_tags=extraction.industry_tags,
        position_tags=extraction.position_tags,
        company_tags=extraction.company_tags,
        raw_keywords=extraction.raw_keywords,
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
    semantic_context: SemanticContext | None = None,
) -> list[MentorCandidateCard]:
    document_list = list(documents)
    if semantic_context and semantic_context.method == "local-scoped-bonus":
        _prepare_scoped_semantic_scores(document_list, profile, semantic_context)
    cards = [
        score_mentor(document, profile, aliases, semantic_context=semantic_context)
        for document in document_list
    ]

    if semantic_context and semantic_context.method == "local-scoped-bonus":
        def compare(left: MentorCandidateCard, right: MentorCandidateCard) -> int:
            left_key = (
                left.rule_score,
                left.structured_score,
                left.raw_text_score,
                len(left.matched_signals.companies),
                len(left.matched_signals.skills),
                len(left.matched_signals.target_mentees),
            )
            right_key = (
                right.rule_score,
                right.structured_score,
                right.raw_text_score,
                len(right.matched_signals.companies),
                len(right.matched_signals.skills),
                len(right.matched_signals.target_mentees),
            )
            if abs(left.final_score - right.final_score) <= 3:
                left_key = (*left_key, left.score_breakdown.global_semantic_score or 0.0)
                right_key = (*right_key, right.score_breakdown.global_semantic_score or 0.0)
            if left_key == right_key:
                return 0
            return -1 if left_key > right_key else 1

        cards.sort(key=cmp_to_key(compare))
    else:
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
    "SemanticContext",
    "ScopedSemanticScores",
    "build_help_student_text",
    "build_reasons",
    "build_role_student_text",
    "build_student_search_text",
    "possible_gap",
    "rank_candidates",
    "score_mentor",
]
