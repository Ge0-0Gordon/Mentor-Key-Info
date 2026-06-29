"""Load simple mentor results into searchable in-memory documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mentor_agent.simple_schemas import SimpleMentorResult


@dataclass(frozen=True)
class MentorDocument:
    result: SimpleMentorResult
    search_text: str
    original_text: str
    mentor_search_text: str


def _flatten(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value) for value in values if value is not None]
    return [str(values)]


def _original_values(result: SimpleMentorResult) -> list[str]:
    payload = result.original_fields.model_dump(by_alias=True)
    return [str(value) for value in payload.values() if value is not None]


def _selected_original_values(result: SimpleMentorResult) -> list[str]:
    original = result.original_fields
    values = [
        original.industry_tags,
        original.coachable_levels,
        original.career_history,
        original.background_experience,
    ]
    return [str(value) for value in values if value is not None]


def build_mentor_document(result: SimpleMentorResult) -> MentorDocument:
    extraction = result.extraction
    standard_industries = [item.tag for item in extraction.industry_tags]
    standard_positions = [item.tag for item in extraction.position_tags]
    position_raw_keywords = [
        keyword
        for item in extraction.position_tags
        for keyword in item.raw_keywords
    ]
    standard_companies = [
        value
        for item in extraction.company_tags
        for value in (item.company_name, item.company_type)
        if value
    ]
    structured_parts = [
        result.mentor_id,
        result.original_fields.mentor_name or "",
        result.original_fields.city or "",
        str(result.original_fields.career_years or ""),
        extraction.summary or "",
        *_flatten(extraction.industries),
        *_flatten(extraction.companies),
        *_flatten(extraction.roles),
        *_flatten(extraction.skills),
        *_flatten(extraction.credentials),
        *_flatten(extraction.education),
        *_flatten(extraction.target_mentees),
        *_flatten(extraction.highlights),
        *_flatten(extraction.keywords),
        *standard_industries,
        *standard_positions,
        *standard_companies,
        *position_raw_keywords,
        *_flatten(extraction.raw_keywords),
    ]
    original_parts = _original_values(result)
    semantic_original_parts = _selected_original_values(result)
    mentor_search_text = " ".join([*structured_parts, *semantic_original_parts])
    return MentorDocument(
        result=result,
        search_text=" ".join([*structured_parts, *original_parts]),
        original_text=" ".join(original_parts),
        mentor_search_text=mentor_search_text,
    )


def load_mentor_documents(path: str | Path) -> list[MentorDocument]:
    documents: list[MentorDocument] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                result = SimpleMentorResult.model_validate_json(line)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid simple mentor result line {line_number}") from exc
            documents.append(build_mentor_document(result))
    return documents


__all__ = ["MentorDocument", "build_mentor_document", "load_mentor_documents"]
