"""Schemas for fast rule-based mentor matching."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mentor_agent.simple_schemas import (
    TaggedCompany,
    TaggedIndustry,
    TaggedPosition,
)


class MatchStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StudentConstraints(MatchStrictModel):
    city: str | None = None
    gender: str | None = None
    seniority: str | None = None


class StudentProfile(MatchStrictModel):
    raw_query: str = ""
    work_years: int | None = Field(default=None, ge=0)
    target_industries: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    current_stage: list[str] = Field(default_factory=list)
    needed_help: list[str] = Field(default_factory=list)
    preferred_background: list[str] = Field(default_factory=list)
    constraints: StudentConstraints = Field(default_factory=StudentConstraints)
    keywords: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    missing_fields: list[str] = Field(default_factory=list)


class MatchedSignal(MatchStrictModel):
    query_term: str
    matched_term: str
    canonical: str | None = None
    source_field: str
    match_type: Literal["exact", "alias", "substring", "raw_text"]
    weight: float = Field(ge=0, le=1)


class MatchedSignals(MatchStrictModel):
    companies: list[MatchedSignal] = Field(default_factory=list)
    roles: list[MatchedSignal] = Field(default_factory=list)
    skills: list[MatchedSignal] = Field(default_factory=list)
    target_mentees: list[MatchedSignal] = Field(default_factory=list)
    industries: list[MatchedSignal] = Field(default_factory=list)
    keywords: list[MatchedSignal] = Field(default_factory=list)


class RuleScoreBreakdown(MatchStrictModel):
    company_match: float = 0
    role_match: float = 0
    skill_match: float = 0
    skill_or_help_match: float = 0
    stage_match: float = 0
    target_mentee_match: float = 0
    years_match: float = 0
    background_match: float = 0
    industry_match: float = 0
    keyword_match: float = 0
    raw_text_match: float = 0
    semantic_match: float | None = None
    rule_role_match: float | None = None
    role_semantic_raw_cosine: float | None = None
    role_semantic_percentile: float | None = None
    role_semantic_bonus: float | None = None
    role_match_final: float | None = None
    rule_skill_match: float | None = None
    help_semantic_raw_cosine: float | None = None
    help_semantic_percentile: float | None = None
    help_semantic_bonus: float | None = None
    skill_match_final: float | None = None
    global_semantic_score: float | None = None
    semantic_fusion_mode: Literal["scoped_bonus"] | None = None
    structured_score: float = 0
    raw_text_score: float = 0
    semantic_score: float | None = None
    relevance_score: float = 0
    availability_factor: float = 1.0
    mentor_quality_factor: float = 1.0
    final_score: float = 0
    total: float = 0


class MentorCandidateCard(MatchStrictModel):
    mentor_id: str
    name: str | None = None
    gender: str | None = None
    city: str | None = None
    years_experience: int | float | str | None = None
    industries: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    target_mentees: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    industry_tags: list[TaggedIndustry] = Field(default_factory=list)
    position_tags: list[TaggedPosition] = Field(default_factory=list)
    company_tags: list[TaggedCompany] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)
    summary: str | None = None
    matched_signals: MatchedSignals = Field(default_factory=MatchedSignals)
    rule_score: float = Field(ge=0, le=100)
    structured_score: float = Field(default=0, ge=0, le=100)
    raw_text_score: float = Field(default=0, ge=0, le=100)
    semantic_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float = Field(default=0, ge=0, le=100)
    score_breakdown: RuleScoreBreakdown = Field(default_factory=RuleScoreBreakdown)


class MentorDisplayCard(MatchStrictModel):
    rank: int = Field(ge=1)
    is_recommended: bool = False
    mentor_id: str
    name: str | None = None
    gender: str | None = None
    city: str | None = None
    years_experience: int | float | str | None = None
    industries: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    target_mentees: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    industry_tags: list[TaggedIndustry] = Field(default_factory=list)
    position_tags: list[TaggedPosition] = Field(default_factory=list)
    company_tags: list[TaggedCompany] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)
    summary: str | None = None


class MatchDebugInfo(MatchStrictModel):
    final_score: float = Field(ge=0, le=100)
    relevance_score: float = Field(default=0, ge=0, le=100)
    rule_rank: int | None = Field(default=None, ge=1)
    llm_rank: int | None = Field(default=None, ge=1)
    llm_fit_score: float | None = Field(default=None, ge=0, le=100)
    score_breakdown: RuleScoreBreakdown = Field(default_factory=RuleScoreBreakdown)
    matched_signals: MatchedSignals = Field(default_factory=MatchedSignals)
    industry_tags: list[TaggedIndustry] = Field(default_factory=list)
    position_tags: list[TaggedPosition] = Field(default_factory=list)
    company_tags: list[TaggedCompany] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)
    possible_gap: str | None = None
    profile_parse_result: StudentProfile
    scoring_version: str = "recommendation-v1"
    rerank_note: str | None = None
    recommendation_reason: list[str] = Field(default_factory=list)


class MatchItem(MatchStrictModel):
    display: MentorDisplayCard
    debug: MatchDebugInfo


class MatchRerankMetadata(MatchStrictModel):
    enabled: bool = False
    method: Literal["none", "llm"] = "none"
    candidate_k: int = 0
    success: bool = False
    fallback_used: bool = False
    latency_ms: int | None = None
    error_message: str | None = None


class MatchSemanticMetadata(MatchStrictModel):
    enabled: bool = False
    method: Literal["none", "fake", "real", "local", "local-scoped-bonus"] = "none"
    embedding_model: str | None = None
    cache_path: str | None = None
    cache_hit_count: int = 0
    cache_miss_count: int = 0


class Recommendation(MatchStrictModel):
    mentor_id: str
    mentor_name: str | None = None
    city: str | None = None
    summary: str | None = None
    rank: int = Field(ge=1)
    match_score: float = Field(ge=0, le=100)
    rule_score: float = Field(ge=0, le=100)
    rerank_score: float | None = Field(default=None, ge=0, le=100)
    matched_signals: MatchedSignals = Field(default_factory=MatchedSignals)
    recommendation_reason: list[str] = Field(default_factory=list)
    possible_gap: str | None = None


class MatchResult(MatchStrictModel):
    query: str
    student_profile: StudentProfile
    total_mentors: int
    candidate_count: int
    returned_count: int
    used_rerank: bool = False
    top_k: int = 10
    scoring_version: str = "recommendation-v1"
    semantic: MatchSemanticMetadata = Field(default_factory=MatchSemanticMetadata)
    rerank: MatchRerankMetadata = Field(default_factory=MatchRerankMetadata)
    results: list[MatchItem] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class ClarificationResult(MatchStrictModel):
    status: Literal["needs_clarification"] = "needs_clarification"
    query: str
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class RerankRecommendation(MatchStrictModel):
    mentor_id: str
    rank: int = Field(ge=1)
    fit_score: float = Field(ge=0, le=100)
    fit_reasons: list[str] = Field(default_factory=list)
    possible_gap: str | None = None


class RerankResponse(MatchStrictModel):
    recommendations: list[RerankRecommendation] = Field(default_factory=list)


class LlmRerankItem(MatchStrictModel):
    mentor_id: str
    rank: int = Field(ge=1)
    llm_fit_score: float | None = Field(default=None, ge=0, le=100)
    rerank_note: str | None = None


class LlmRerankResponse(MatchStrictModel):
    ranked_ids: list[str] = Field(default_factory=list)
    ordered_mentor_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    reranked_results: list[LlmRerankItem] = Field(default_factory=list)


__all__ = [
    "ClarificationResult",
    "MatchedSignal",
    "MatchedSignals",
    "MatchResult",
    "MatchDebugInfo",
    "MatchItem",
    "MatchRerankMetadata",
    "MatchSemanticMetadata",
    "MentorDisplayCard",
    "MentorCandidateCard",
    "Recommendation",
    "RerankRecommendation",
    "RerankResponse",
    "LlmRerankItem",
    "LlmRerankResponse",
    "RuleScoreBreakdown",
    "StudentConstraints",
    "StudentProfile",
]
