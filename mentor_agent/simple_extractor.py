"""Fast single-mentor keyword extraction without evidence or mapping logic."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .evidence import normalize_loose_text
from .extractor import ExtractionError
from .schemas import MentorInput, SourceMetadata
from .simple_prompts import (
    build_simple_batch_extraction_messages,
    build_simple_extraction_messages,
    build_tagged_simple_batch_extraction_messages,
    build_tagged_simple_extraction_messages,
)
from .simple_schemas import (
    MAX_ITEMS_PER_CATEGORY,
    MAX_SUMMARY_CHARS,
    MAX_TEXT_CHARS,
    SIMPLE_BATCH_SCHEMA_VERSION,
    SIMPLE_PROMPT_VERSION,
    SIMPLE_SCHEMA_VERSION,
    TAGGED_SIMPLE_PROMPT_VERSION,
    PositionRelationType,
    SimpleBatchExtractionResponse,
    SimpleMentorExtraction,
    SimpleMentorBatchResult,
    SimpleMentorResult,
)
from .tag_taxonomy import TagTaxonomy


_LIST_FIELDS = (
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
)

_TAG_EVIDENCE_FIELDS = (
    "行业标签",
    "从业经历",
    "背景经验",
    "可辅导学员职级",
)


def _invoke_model(model_client: Any, messages: list[dict[str, str]]) -> Any:
    invoke = getattr(model_client, "invoke", None)
    if callable(invoke):
        return invoke(messages)
    if callable(model_client):
        return model_client(messages)
    raise TypeError("model_client must be callable or expose invoke(messages)")


def _response_content(response: Any) -> Any:
    content = getattr(response, "content", None)
    if content is not None:
        return content
    if isinstance(response, Mapping) and set(response) == {"content"}:
        return response["content"]
    return response


def _unique_clean_strings(values: Any) -> Any:
    if not isinstance(values, list):
        return values

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        text = text[:MAX_TEXT_CHARS]
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= MAX_ITEMS_PER_CATEGORY:
            break
    return cleaned


def clean_simple_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove recoverable noise before Pydantic validation."""

    cleaned = dict(payload)
    for field_name in _LIST_FIELDS:
        if field_name in cleaned:
            cleaned[field_name] = _unique_clean_strings(cleaned[field_name])

    if "summary" in cleaned:
        summary = cleaned["summary"]
        if summary is None:
            cleaned["summary"] = None
        elif isinstance(summary, str):
            summary = summary.strip()
            cleaned["summary"] = summary[:MAX_SUMMARY_CHARS] if summary else None
    return cleaned


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _review_reason(path: str, tag: str | None, reason: str) -> str:
    return f"{path}|tag={tag or '<missing>'}|reason={reason}"


def _evidence_is_valid(evidence: str, mentor_input: MentorInput) -> bool:
    normalized_evidence = normalize_loose_text(evidence)
    if not normalized_evidence:
        return False
    source = mentor_input.original_fields.model_dump(by_alias=True)
    for field_name in _TAG_EVIDENCE_FIELDS:
        value = source.get(field_name)
        if value is None:
            continue
        if normalized_evidence in normalize_loose_text(str(value)):
            return True
    return False


def _valid_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    parsed = float(value)
    return parsed if 0 <= parsed <= 1 else None


def _structured_items(
    payload: Mapping[str, Any],
    field_name: str,
    reasons: list[str],
) -> list[Any]:
    value = payload.get(field_name, [])
    if isinstance(value, list):
        return value
    reasons.append(_review_reason(field_name, None, "invalid_list"))
    return []


def _deduplicate_tag_items(
    items: list[tuple[int, dict[str, Any]]],
    *,
    field_name: str,
    reasons: list[str],
    conflict_key: str | None = None,
) -> list[dict[str, Any]]:
    selected: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, item in items:
        key = str(item.get("tag") or item.get("company_name")).casefold()
        existing = selected.get(key)
        if existing is None:
            selected[key] = (index, item)
            continue
        previous_index, previous = existing
        if (
            conflict_key
            and previous.get(conflict_key) != item.get(conflict_key)
        ):
            reasons.append(
                _review_reason(
                    f"{field_name}[{index}]",
                    str(item.get("tag") or item.get("company_name")),
                    "duplicate_conflicting_relation",
                )
            )
        if item["confidence"] > previous["confidence"]:
            selected[key] = (index, item)
        elif item["confidence"] == previous["confidence"] and index < previous_index:
            selected[key] = (index, item)
    return [
        item
        for _, item in sorted(selected.values(), key=lambda selected_item: selected_item[0])
    ]


def sanitize_tagged_payload(
    payload: Mapping[str, Any],
    mentor_input: MentorInput,
    taxonomy: TagTaxonomy,
    *,
    confidence_threshold: float = 0.70,
) -> dict[str, Any]:
    """Return canonical tagged output and program-computed review metadata."""

    if not 0 <= confidence_threshold <= 1:
        raise ValueError("confidence_threshold must be between 0 and 1")

    cleaned = clean_simple_payload(payload)
    reasons: list[str] = []
    industry_candidates = set(taxonomy.industry_tags)
    position_candidates = set(taxonomy.position_tags)

    industry_items: list[tuple[int, dict[str, Any]]] = []
    for index, raw_item in enumerate(
        _structured_items(payload, "industry_tags", reasons)
    ):
        path = f"industry_tags[{index}]"
        if not isinstance(raw_item, Mapping):
            reasons.append(_review_reason(path, None, "invalid_item"))
            continue
        tag = _clean_optional_text(raw_item.get("tag"))
        if tag not in industry_candidates:
            reasons.append(_review_reason(path, tag, "tag_not_in_taxonomy"))
            continue
        evidence = _clean_optional_text(raw_item.get("evidence"))
        if evidence is None:
            reasons.append(_review_reason(path, tag, "evidence_empty"))
            continue
        if not _evidence_is_valid(evidence, mentor_input):
            reasons.append(
                _review_reason(path, tag, "evidence_not_found_in_source")
            )
            continue
        confidence = _valid_confidence(raw_item.get("confidence"))
        if confidence is None:
            reasons.append(_review_reason(path, tag, "invalid_confidence"))
            continue
        if confidence < confidence_threshold:
            reasons.append(
                _review_reason(path, tag, "confidence_below_threshold")
            )
        industry_items.append(
            (
                index,
                {
                    "tag": tag,
                    "confidence": confidence,
                    "evidence": evidence,
                },
            )
        )

    position_items: list[tuple[int, dict[str, Any]]] = []
    valid_relations = {relation.value for relation in PositionRelationType}
    for index, raw_item in enumerate(
        _structured_items(payload, "position_tags", reasons)
    ):
        path = f"position_tags[{index}]"
        if not isinstance(raw_item, Mapping):
            reasons.append(_review_reason(path, None, "invalid_item"))
            continue
        tag = _clean_optional_text(raw_item.get("tag"))
        if tag not in position_candidates:
            reasons.append(_review_reason(path, tag, "tag_not_in_taxonomy"))
            continue
        evidence = _clean_optional_text(raw_item.get("evidence"))
        if evidence is None:
            reasons.append(_review_reason(path, tag, "evidence_empty"))
            continue
        if not _evidence_is_valid(evidence, mentor_input):
            reasons.append(
                _review_reason(path, tag, "evidence_not_found_in_source")
            )
            continue
        relation_type = _clean_optional_text(raw_item.get("relation_type"))
        if relation_type not in valid_relations:
            reasons.append(_review_reason(path, tag, "invalid_relation_type"))
            continue
        confidence = _valid_confidence(raw_item.get("confidence"))
        if confidence is None:
            reasons.append(_review_reason(path, tag, "invalid_confidence"))
            continue
        if confidence < confidence_threshold:
            reasons.append(
                _review_reason(path, tag, "confidence_below_threshold")
            )
        position_items.append(
            (
                index,
                {
                    "tag": tag,
                    "relation_type": relation_type,
                    "confidence": confidence,
                    "raw_keywords": _unique_clean_strings(
                        raw_item.get("raw_keywords", [])
                    ),
                    "evidence": evidence,
                },
            )
        )

    company_items: list[tuple[int, dict[str, Any]]] = []
    for index, raw_item in enumerate(
        _structured_items(payload, "company_tags", reasons)
    ):
        path = f"company_tags[{index}]"
        if not isinstance(raw_item, Mapping):
            reasons.append(_review_reason(path, None, "invalid_item"))
            continue
        company_name = _clean_optional_text(raw_item.get("company_name"))
        if company_name is None:
            reasons.append(_review_reason(path, None, "company_name_empty"))
            continue
        evidence = _clean_optional_text(raw_item.get("evidence"))
        if evidence is None:
            reasons.append(_review_reason(path, company_name, "evidence_empty"))
            continue
        if not _evidence_is_valid(evidence, mentor_input):
            reasons.append(
                _review_reason(
                    path,
                    company_name,
                    "evidence_not_found_in_source",
                )
            )
            continue
        industry_tag = _clean_optional_text(raw_item.get("industry_tag"))
        if industry_tag is not None and industry_tag not in industry_candidates:
            reasons.append(
                _review_reason(path, company_name, "tag_not_in_taxonomy")
            )
            continue
        confidence = _valid_confidence(raw_item.get("confidence"))
        if confidence is None:
            reasons.append(
                _review_reason(path, company_name, "invalid_confidence")
            )
            continue
        if confidence < confidence_threshold:
            reasons.append(
                _review_reason(
                    path,
                    company_name,
                    "confidence_below_threshold",
                )
            )
        company_items.append(
            (
                index,
                {
                    "company_name": company_name,
                    "company_type": _clean_optional_text(
                        raw_item.get("company_type")
                    ),
                    "industry_tag": industry_tag,
                    "evidence": evidence,
                    "confidence": confidence,
                },
            )
        )

    cleaned["industry_tags"] = _deduplicate_tag_items(
        industry_items,
        field_name="industry_tags",
        reasons=reasons,
    )
    cleaned["position_tags"] = _deduplicate_tag_items(
        position_items,
        field_name="position_tags",
        reasons=reasons,
        conflict_key="relation_type",
    )
    cleaned["company_tags"] = _deduplicate_tag_items(
        company_items,
        field_name="company_tags",
        reasons=reasons,
    )
    cleaned["review_reasons"] = list(dict.fromkeys(reasons))
    cleaned["review_required"] = bool(cleaned["review_reasons"])
    return cleaned


def _parse_simple_extraction(
    response: Any,
    mentor_input: MentorInput,
    *,
    taxonomy: TagTaxonomy | None = None,
    confidence_threshold: float = 0.70,
) -> SimpleMentorExtraction:
    content = _response_content(response)
    if isinstance(content, str):
        payload = json.loads(content)
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        raise TypeError("model response must be JSON text, a mapping, or expose content")
    if not isinstance(payload, Mapping):
        raise TypeError("model response JSON must be an object")
    cleaned = (
        sanitize_tagged_payload(
            payload,
            mentor_input,
            taxonomy,
            confidence_threshold=confidence_threshold,
        )
        if taxonomy is not None
        else clean_simple_payload(payload)
    )
    return SimpleMentorExtraction.model_validate(cleaned)


def _payload_from_response(response: Any) -> Mapping[str, Any]:
    content = _response_content(response)
    if isinstance(content, str):
        payload = json.loads(content)
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        raise TypeError("model response must be JSON text, a mapping, or expose content")
    if not isinstance(payload, Mapping):
        raise TypeError("model response JSON must be an object")
    return payload


def _parse_simple_batch_response(
    response: Any,
    mentor_inputs: list[MentorInput],
    *,
    taxonomy: TagTaxonomy | None = None,
    confidence_threshold: float = 0.70,
) -> SimpleBatchExtractionResponse:
    payload = dict(_payload_from_response(response))
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("simple batch response must contain a results list")

    input_by_id = {
        mentor_input.mentor_id: mentor_input for mentor_input in mentor_inputs
    }
    cleaned_results = []
    for item in raw_results:
        if not isinstance(item, Mapping):
            raise ValueError("simple batch result item must be an object")
        extraction = item.get("extraction")
        if not isinstance(extraction, Mapping):
            raise ValueError("simple batch result item must contain extraction")
        mentor_id = item.get("mentor_id")
        mentor_input = input_by_id.get(mentor_id)
        if mentor_input is None:
            cleaned_extraction = clean_simple_payload(extraction)
        elif taxonomy is not None:
            cleaned_extraction = sanitize_tagged_payload(
                extraction,
                mentor_input,
                taxonomy,
                confidence_threshold=confidence_threshold,
            )
        else:
            cleaned_extraction = clean_simple_payload(extraction)
        cleaned_results.append(
            {
                "mentor_id": mentor_id,
                "extraction": cleaned_extraction,
            }
        )
    parsed = SimpleBatchExtractionResponse.model_validate(
        {"results": cleaned_results}
    )

    input_ids = [mentor_input.mentor_id for mentor_input in mentor_inputs]
    output_ids = [item.mentor_id for item in parsed.results]
    if len(output_ids) != len(set(output_ids)):
        raise ValueError("simple batch response contains duplicate mentor_id")
    if set(output_ids) != set(input_ids):
        missing = sorted(set(input_ids) - set(output_ids))
        extra = sorted(set(output_ids) - set(input_ids))
        raise ValueError(
            f"simple batch mentor_id mismatch: missing={len(missing)}, extra={len(extra)}"
        )
    return parsed


def _build_simple_result(
    mentor_input: MentorInput,
    extraction: SimpleMentorExtraction,
    *,
    model_service_name: str,
    model_name: str | None,
    attempt_count: int,
    latency_ms: int,
    taxonomy: TagTaxonomy | None = None,
) -> SimpleMentorResult:
    return SimpleMentorResult(
        schema_version=SIMPLE_SCHEMA_VERSION,
        prompt_version=(
            TAGGED_SIMPLE_PROMPT_VERSION
            if taxonomy is not None
            else SIMPLE_PROMPT_VERSION
        ),
        standard_tags_enabled=taxonomy is not None,
        taxonomy_hash=taxonomy.taxonomy_hash if taxonomy is not None else None,
        mentor_id=mentor_input.mentor_id,
        record_hash=mentor_input.record_hash,
        source=SourceMetadata(
            file=mentor_input.source_file,
            sheet=mentor_input.source_sheet,
            row=mentor_input.source_row,
        ),
        original_fields=mentor_input.original_fields,
        extraction=extraction,
        processing={
            "status": "success",
            "attempt_count": attempt_count,
            "processed_at": datetime.now(timezone.utc),
            "model_service_name": model_service_name,
            "model_name": model_name,
            "latency_ms": latency_ms,
        },
    )


def extract_simple_mentor_with_model(
    mentor_input: MentorInput,
    model_client: Any,
    *,
    max_attempts: int = 1,
    model_service_name: str = "injected-model-client",
    model_name: str | None = None,
    taxonomy: TagTaxonomy | None = None,
    review_confidence_threshold: float = 0.70,
) -> SimpleMentorResult:
    """Extract flat keywords for one mentor without evidence validation."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    messages = (
        build_tagged_simple_extraction_messages(mentor_input, taxonomy)
        if taxonomy is not None
        else build_simple_extraction_messages(mentor_input)
    )
    started = perf_counter()
    last_error: Exception | None = None
    extraction: SimpleMentorExtraction | None = None
    attempt_count = 0

    for attempt_count in range(1, max_attempts + 1):
        try:
            response = _invoke_model(model_client, messages)
            extraction = _parse_simple_extraction(
                response,
                mentor_input,
                taxonomy=taxonomy,
                confidence_threshold=review_confidence_threshold,
            )
            break
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

    if extraction is None:
        raise ExtractionError(
            f"simple mentor extraction failed after {max_attempts} attempt(s)"
        ) from last_error

    latency_ms = max(0, int((perf_counter() - started) * 1000))
    return _build_simple_result(
        mentor_input,
        extraction,
        model_service_name=model_service_name,
        model_name=model_name,
        attempt_count=attempt_count,
        latency_ms=latency_ms,
        taxonomy=taxonomy,
    )


def extract_simple_mentor(
    mentor_input: MentorInput,
    model_client: Callable[[Sequence[Mapping[str, str]]], Any] | Any,
    **kwargs: Any,
) -> SimpleMentorResult:
    """Public simple-mode single-record extraction entry point."""

    return extract_simple_mentor_with_model(mentor_input, model_client, **kwargs)


def extract_simple_mentor_batch(
    mentor_inputs: Sequence[MentorInput],
    model_client: Callable[[Sequence[Mapping[str, str]]], Any] | Any,
    *,
    max_attempts: int = 1,
    model_service_name: str = "injected-model-client",
    model_name: str | None = None,
    taxonomy: TagTaxonomy | None = None,
    review_confidence_threshold: float = 0.70,
) -> list[SimpleMentorResult]:
    """Extract flat keywords for multiple mentors in one model call."""

    mentor_input_list = list(mentor_inputs)
    if not mentor_input_list:
        return []
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    input_ids = [mentor_input.mentor_id for mentor_input in mentor_input_list]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("mentor_inputs contains duplicate mentor_id")

    messages = (
        build_tagged_simple_batch_extraction_messages(
            mentor_input_list,
            taxonomy,
        )
        if taxonomy is not None
        else build_simple_batch_extraction_messages(mentor_input_list)
    )
    started = perf_counter()
    last_error: Exception | None = None
    parsed: SimpleBatchExtractionResponse | None = None
    attempt_count = 0

    for attempt_count in range(1, max_attempts + 1):
        try:
            response = _invoke_model(model_client, messages)
            parsed = _parse_simple_batch_response(
                response,
                mentor_input_list,
                taxonomy=taxonomy,
                confidence_threshold=review_confidence_threshold,
            )
            break
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

    if parsed is None:
        raise ExtractionError(
            f"simple batch extraction failed after {max_attempts} attempt(s)"
        ) from last_error

    latency_ms = max(0, int((perf_counter() - started) * 1000))
    input_by_id = {mentor_input.mentor_id: mentor_input for mentor_input in mentor_input_list}
    return [
        _build_simple_result(
            input_by_id[item.mentor_id],
            item.extraction,
            model_service_name=model_service_name,
            model_name=model_name,
            attempt_count=attempt_count,
            latency_ms=latency_ms,
            taxonomy=taxonomy,
        )
        for item in parsed.results
    ]


def make_simple_batch_result(
    results: list[SimpleMentorResult],
) -> SimpleMentorBatchResult:
    """Wrap program-assembled simple results for HTTP response content."""

    return SimpleMentorBatchResult(
        schema_version=SIMPLE_BATCH_SCHEMA_VERSION,
        results=results,
    )


__all__ = [
    "clean_simple_payload",
    "extract_simple_mentor_batch",
    "extract_simple_mentor",
    "extract_simple_mentor_with_model",
    "make_simple_batch_result",
    "sanitize_tagged_payload",
]
