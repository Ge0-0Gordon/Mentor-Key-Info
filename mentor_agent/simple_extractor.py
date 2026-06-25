"""Fast single-mentor keyword extraction without evidence or mapping logic."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .extractor import ExtractionError
from .schemas import MentorInput, SourceMetadata
from .simple_prompts import (
    build_simple_batch_extraction_messages,
    build_simple_extraction_messages,
)
from .simple_schemas import (
    MAX_ITEMS_PER_CATEGORY,
    MAX_SUMMARY_CHARS,
    MAX_TEXT_CHARS,
    SIMPLE_BATCH_SCHEMA_VERSION,
    SIMPLE_PROMPT_VERSION,
    SIMPLE_SCHEMA_VERSION,
    SimpleBatchExtractionResponse,
    SimpleMentorExtraction,
    SimpleMentorBatchResult,
    SimpleMentorResult,
)


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


def _parse_simple_extraction(response: Any) -> SimpleMentorExtraction:
    content = _response_content(response)
    if isinstance(content, str):
        payload = json.loads(content)
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        raise TypeError("model response must be JSON text, a mapping, or expose content")
    if not isinstance(payload, Mapping):
        raise TypeError("model response JSON must be an object")
    return SimpleMentorExtraction.model_validate(clean_simple_payload(payload))


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
) -> SimpleBatchExtractionResponse:
    payload = dict(_payload_from_response(response))
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("simple batch response must contain a results list")

    cleaned_results = []
    for item in raw_results:
        if not isinstance(item, Mapping):
            raise ValueError("simple batch result item must be an object")
        extraction = item.get("extraction")
        if not isinstance(extraction, Mapping):
            raise ValueError("simple batch result item must contain extraction")
        cleaned_results.append(
            {
                "mentor_id": item.get("mentor_id"),
                "extraction": clean_simple_payload(extraction),
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
) -> SimpleMentorResult:
    return SimpleMentorResult(
        schema_version=SIMPLE_SCHEMA_VERSION,
        prompt_version=SIMPLE_PROMPT_VERSION,
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
) -> SimpleMentorResult:
    """Extract flat keywords for one mentor without evidence validation."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    messages = build_simple_extraction_messages(mentor_input)
    started = perf_counter()
    last_error: Exception | None = None
    extraction: SimpleMentorExtraction | None = None
    attempt_count = 0

    for attempt_count in range(1, max_attempts + 1):
        try:
            response = _invoke_model(model_client, messages)
            extraction = _parse_simple_extraction(response)
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

    messages = build_simple_batch_extraction_messages(mentor_input_list)
    started = perf_counter()
    last_error: Exception | None = None
    parsed: SimpleBatchExtractionResponse | None = None
    attempt_count = 0

    for attempt_count in range(1, max_attempts + 1):
        try:
            response = _invoke_model(model_client, messages)
            parsed = _parse_simple_batch_response(response, mentor_input_list)
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
]
