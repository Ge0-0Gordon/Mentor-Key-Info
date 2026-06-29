"""Small data contracts for fast keyword-only mentor extraction."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator

from .schemas import OriginalFields, ProcessingMetadata, SourceMetadata, StrictModel


MAX_ITEMS_PER_CATEGORY = 20
MAX_TEXT_CHARS = 80
MAX_SUMMARY_CHARS = 120
SIMPLE_SCHEMA_VERSION = "simple-v1"
SIMPLE_PROMPT_VERSION = "mentor-simple-v1"
TAGGED_SIMPLE_PROMPT_VERSION = "mentor-simple-tagged-v1"
SIMPLE_BATCH_SCHEMA_VERSION = "simple-batch-v1"


class PositionRelationType(str, Enum):
    FIRSTHAND_ROLE = "firsthand_role"
    MANAGED_TEAM = "managed_team"
    RECRUITED_OR_EVALUATED = "recruited_or_evaluated"
    RELATED = "related"


class TaggedIndustry(StrictModel):
    tag: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1)


class TaggedPosition(StrictModel):
    tag: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    relation_type: PositionRelationType
    confidence: float = Field(ge=0, le=1)
    raw_keywords: list[str] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_CATEGORY,
    )
    evidence: str = Field(min_length=1)

    @field_validator("raw_keywords")
    @classmethod
    def _raw_keywords_must_be_text(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("raw_keywords must be non-empty strings")
        return values


class TaggedCompany(StrictModel):
    company_name: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    company_type: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    industry_tag: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class SimpleMentorExtraction(StrictModel):
    """Flat keyword extraction produced by the model in simple mode."""

    industries: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    companies: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    roles: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    skills: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    credentials: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    education: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    target_mentees: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    highlights: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    keywords: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_CATEGORY)
    industry_tags: list[TaggedIndustry] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_CATEGORY,
    )
    position_tags: list[TaggedPosition] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_CATEGORY,
    )
    company_tags: list[TaggedCompany] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_CATEGORY,
    )
    raw_keywords: list[str] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_CATEGORY,
    )
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=MAX_SUMMARY_CHARS)

    @field_validator(
        "industries",
        "companies",
        "roles",
        "skills",
        "credentials",
        "education",
        "target_mentees",
        "highlights",
        "keywords",
        "raw_keywords",
        "review_reasons",
    )
    @classmethod
    def _items_must_be_text(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("items must be non-empty strings")
        return values


class SimpleMentorResult(StrictModel):
    """Program-assembled result for simple keyword extraction."""

    schema_version: Literal["simple-v1"]
    prompt_version: Literal["mentor-simple-v1", "mentor-simple-tagged-v1"]
    standard_tags_enabled: bool = False
    taxonomy_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    mentor_id: str = Field(min_length=1)
    record_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source: SourceMetadata
    original_fields: OriginalFields
    extraction: SimpleMentorExtraction
    processing: ProcessingMetadata


class SimpleBatchExtractionItem(StrictModel):
    """One model-produced extraction item inside a simple batch response."""

    mentor_id: str = Field(min_length=1)
    extraction: SimpleMentorExtraction


class SimpleBatchExtractionResponse(StrictModel):
    """Model response shape for simple batch extraction."""

    results: list[SimpleBatchExtractionItem] = Field(default_factory=list)


class SimpleMentorBatchResult(StrictModel):
    """Program-assembled HTTP response for simple batch extraction."""

    schema_version: Literal["simple-batch-v1"]
    results: list[SimpleMentorResult] = Field(default_factory=list)


__all__ = [
    "MAX_ITEMS_PER_CATEGORY",
    "MAX_SUMMARY_CHARS",
    "MAX_TEXT_CHARS",
    "SIMPLE_BATCH_SCHEMA_VERSION",
    "SIMPLE_PROMPT_VERSION",
    "SIMPLE_SCHEMA_VERSION",
    "TAGGED_SIMPLE_PROMPT_VERSION",
    "PositionRelationType",
    "SimpleBatchExtractionItem",
    "SimpleBatchExtractionResponse",
    "SimpleMentorBatchResult",
    "SimpleMentorExtraction",
    "SimpleMentorResult",
    "TaggedCompany",
    "TaggedIndustry",
    "TaggedPosition",
]
