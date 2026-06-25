"""Schemas for fast rule-based mentor matching."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StudentConstraints(MatchStrictModel):
    city: str | None = None
    gender: str | None = None
    seniority: str | None = None


class StudentProfile(MatchStrictModel):
    raw_query: str = Field(min_length=1)
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
    skill_or_help_match: float = 0
    target_mentee_match: float = 0
    industry_match: float = 0
    keyword_match: float = 0
    structured_score: float = 0
    raw_text_score: float = 0
    semantic_score: float | None = None
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
    summary: str | None = None


class MatchDebugInfo(MatchStrictModel):
    final_score: float = Field(ge=0, le=100)
    score_breakdown: RuleScoreBreakdown = Field(default_factory=RuleScoreBreakdown)
    matched_signals: MatchedSignals = Field(default_factory=MatchedSignals)
    possible_gap: str | None = None
    profile_parse_result: StudentProfile
    scoring_version: str = "matching-v1"
    recommendation_reason: list[str] = Field(default_factory=list)


class MatchItem(MatchStrictModel):
    display: MentorDisplayCard
    debug: MatchDebugInfo


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
    scoring_version: str = "matching-v1"
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


__all__ = [
    "ClarificationResult",
    "MatchedSignal",
    "MatchedSignals",
    "MatchResult",
    "MatchDebugInfo",
    "MatchItem",
    "MentorDisplayCard",
    "MentorCandidateCard",
    "Recommendation",
    "RerankRecommendation",
    "RerankResponse",
    "RuleScoreBreakdown",
    "StudentConstraints",
    "StudentProfile",
]
