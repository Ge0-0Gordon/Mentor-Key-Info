"""Single-mentor structured extraction with injectable model invocation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .evidence import validate_evidence
from .normalizers import (
    deduplicate_items,
    normalize_company_name,
    normalize_industry,
    normalize_skill,
)
from .prompts import (
    INDUSTRY_TAXONOMY_VERSION,
    MENTOR_EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SOFT_INDUSTRY_TAXONOMY,
)
from .schemas import (
    CredentialStatus,
    EvidenceMatchType,
    MappingStatus,
    MentorExtraction,
    MentorInput,
    MentorResult,
    NormalizedProfile,
    OrganizationRelationship,
    OriginalFields,
    QualityIssue,
    SourceMetadata,
    StandardizedValue,
)


class ExtractionError(RuntimeError):
    """Raised after the configured single-record extraction attempts fail."""


_EXTRACTION_LIST_FIELDS = (
    "industry_tags",
    "career_experiences",
    "skills",
    "credentials_and_awards",
    "education",
    "target_mentees",
    "career_highlights",
)

_EMPLOYMENT_MARKERS = ("曾任", "历任", "任职", "就职", "曾在", "加入", "担任")
_PROJECT_MARKERS = ("项目", "参与", "交付")
_CLIENT_MARKERS = ("服务", "客户", "提供咨询", "提供服务")
_PARTNER_MARKERS = ("合作", "联合")
_CREDENTIAL_OWNERSHIP_MARKERS = ("持有", "获得", "通过", "获评", "荣获", "取得", "获证")


def build_extraction_messages(mentor_input: MentorInput) -> list[dict[str, str]]:
    """Build system and final user messages for one MentorInput."""

    user_payload = {
        "instruction": "根据 mentor_input 抽取 MentorExtraction，只返回符合 output_schema 的 JSON。",
        "output_schema": MentorExtraction.model_json_schema(),
        "mentor_input": mentor_input.model_dump(by_alias=True, mode="json"),
    }
    return [
        {"role": "system", "content": MENTOR_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
        },
    ]


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


def _parse_extraction(response: Any) -> MentorExtraction:
    content = _response_content(response)
    if isinstance(content, str):
        payload = json.loads(content)
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        raise TypeError("model response must be JSON text, a mapping, or expose content")
    return MentorExtraction.model_validate(payload)


def _quality_issue(
    code: str,
    message: str,
    *,
    path: str | None = None,
    source_field: Any = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity="warning",
        path=path,
        source_field=source_field,
        message=message,
    )


def _validate_item_evidence(
    item: Any,
    path: str,
    original_fields: OriginalFields,
    quality_issues: list[QualityIssue],
) -> Any | None:
    valid_evidence = []
    for evidence_index, evidence in enumerate(item.evidence):
        evidence_path = f"{path}.evidence[{evidence_index}]"
        checked = validate_evidence(evidence, original_fields)
        if checked.match_type is EvidenceMatchType.STRICT:
            valid_evidence.append(checked)
        elif checked.match_type is EvidenceMatchType.LOOSE:
            valid_evidence.append(checked)
            quality_issues.append(
                _quality_issue(
                    "loose_evidence_match",
                    "Evidence 仅在有限字符归一后匹配原字段，请按需人工复核。",
                    path=evidence_path,
                    source_field=checked.source_field,
                )
            )
        else:
            quality_issues.append(
                _quality_issue(
                    "invalid_evidence",
                    "Evidence 无法在声明的 source_field 中匹配，已从该抽取项移除。",
                    path=evidence_path,
                    source_field=checked.source_field,
                )
            )

    if not valid_evidence:
        quality_issues.append(
            _quality_issue(
                "extracted_item_dropped",
                "抽取项没有任何有效 evidence，已从可信结果中删除。",
                path=path,
            )
        )
        return None
    return item.model_copy(update={"evidence": valid_evidence})


def _validate_extraction_evidence(
    extraction: MentorExtraction,
    original_fields: OriginalFields,
) -> tuple[MentorExtraction, list[QualityIssue]]:
    quality_issues: list[QualityIssue] = []
    updates: dict[str, Any] = {}

    for field_name in _EXTRACTION_LIST_FIELDS:
        validated_items = []
        for index, item in enumerate(getattr(extraction, field_name)):
            validated = _validate_item_evidence(
                item,
                f"{field_name}[{index}]",
                original_fields,
                quality_issues,
            )
            if validated is not None:
                validated_items.append(validated)
        updates[field_name] = validated_items

    if extraction.summary is not None:
        updates["summary"] = _validate_item_evidence(
            extraction.summary,
            "summary",
            original_fields,
            quality_issues,
        )

    return extraction.model_copy(update=updates), quality_issues


def _relationship_from_evidence(item: Any) -> OrganizationRelationship:
    evidence_text = " ".join(evidence.quote for evidence in item.evidence)
    if any(marker in evidence_text for marker in _EMPLOYMENT_MARKERS):
        return OrganizationRelationship.EMPLOYER
    if any(marker in evidence_text for marker in _PROJECT_MARKERS):
        return OrganizationRelationship.PROJECT
    if any(marker in evidence_text for marker in _CLIENT_MARKERS):
        return OrganizationRelationship.CLIENT
    if any(marker in evidence_text for marker in _PARTNER_MARKERS):
        return OrganizationRelationship.PARTNER
    return OrganizationRelationship.UNKNOWN


def _normalize_and_guard(
    extraction: MentorExtraction,
    quality_issues: list[QualityIssue],
) -> MentorExtraction:
    industries = []
    for item in extraction.industry_tags:
        normalized = normalize_industry(item.raw_industry)
        industry_category = item.industry_category
        if (
            normalized.mapping_status is MappingStatus.MAPPED
            and normalized.normalized_value in SOFT_INDUSTRY_TAXONOMY
        ):
            industry_category = normalized.normalized_value
        industries.append(
            item.model_copy(
                update={
                    "normalized_industry": normalized.normalized_value,
                    "mapping_status": normalized.mapping_status,
                    "industry_category": industry_category,
                }
            )
        )

    career_experiences = []
    for index, item in enumerate(extraction.career_experiences):
        normalized = normalize_company_name(item.raw_name)
        relationship = item.relationship
        if relationship is OrganizationRelationship.EMPLOYER:
            supported_relationship = _relationship_from_evidence(item)
            if supported_relationship is not OrganizationRelationship.EMPLOYER:
                relationship = supported_relationship
                quality_issues.append(
                    _quality_issue(
                        "relationship_corrected",
                        "原文不支持 employer，已按 evidence 语境纠正组织关系。",
                        path=f"career_experiences[{index}].relationship",
                    )
                )
        career_experiences.append(
            item.model_copy(
                update={
                    "normalized_name": normalized.normalized_value,
                    "mapping_status": normalized.mapping_status,
                    "relationship": relationship,
                }
            )
        )

    skills = []
    for item in extraction.skills:
        normalized = normalize_skill(item.raw_skill)
        skills.append(
            item.model_copy(
                update={
                    "normalized_skill": normalized.normalized_value,
                    "mapping_status": normalized.mapping_status,
                }
            )
        )

    credentials = []
    for index, item in enumerate(extraction.credentials_and_awards):
        evidence_text = " ".join(evidence.quote for evidence in item.evidence)
        describes_system_building = bool(
            re.search(r"(搭建|建设|建立).{0,8}认证体系|认证体系.{0,8}(搭建|建设)", evidence_text)
        )
        has_personal_ownership = any(
            marker in evidence_text for marker in _CREDENTIAL_OWNERSHIP_MARKERS
        )
        if describes_system_building and not has_personal_ownership:
            quality_issues.append(
                _quality_issue(
                    "credential_not_personally_held",
                    "原文描述认证体系建设，不支持导师本人持证，已删除该项。",
                    path=f"credentials_and_awards[{index}]",
                )
            )
            quality_issues.append(
                _quality_issue(
                    "extracted_item_dropped",
                    "该资质项缺少本人持有或获得的证据，已从可信结果中删除。",
                    path=f"credentials_and_awards[{index}]",
                )
            )
            continue

        if (
            item.credential_status is CredentialStatus.HELD
            and re.search(r"准\s*PCC|准认证", evidence_text, flags=re.IGNORECASE)
        ):
            item = item.model_copy(
                update={"credential_status": CredentialStatus.CANDIDATE}
            )
            quality_issues.append(
                _quality_issue(
                    "credential_status_corrected",
                    "准认证状态不能标为 held，已纠正为 candidate。",
                    path=f"credentials_and_awards[{index}].credential_status",
                )
            )
        credentials.append(item)

    return extraction.model_copy(
        update={
            "industry_tags": deduplicate_items(
                industries,
                key=lambda item: (
                    item.raw_industry,
                    item.normalized_industry,
                ),
            ),
            "career_experiences": deduplicate_items(
                career_experiences,
                key=lambda item: (
                    item.raw_name,
                    item.normalized_name,
                    item.relationship.value,
                ),
            ),
            "skills": deduplicate_items(
                skills,
                key=lambda item: (item.raw_skill, item.normalized_skill),
            ),
            "credentials_and_awards": credentials,
        }
    )


def _normalized_profile(original_fields: OriginalFields) -> NormalizedProfile:
    name = None
    if original_fields.mentor_name:
        name = StandardizedValue(
            raw_value=original_fields.mentor_name,
            normalized_value=original_fields.mentor_name.strip(),
            mapping_status="mapped",
        )

    gender = None
    if original_fields.gender:
        gender = StandardizedValue(
            raw_value=original_fields.gender,
            normalized_value=original_fields.gender.strip(),
            mapping_status="mapped",
        )

    locations = []
    if original_fields.city:
        locations.append(
            StandardizedValue(
                raw_value=original_fields.city,
                normalized_value=original_fields.city.strip(),
                mapping_status="mapped",
            )
        )

    career_years = None
    raw_years = original_fields.career_years
    if isinstance(raw_years, (int, float)) and not isinstance(raw_years, bool):
        if float(raw_years).is_integer() and raw_years >= 0:
            career_years = int(raw_years)
    elif isinstance(raw_years, str) and raw_years.strip().isdigit():
        career_years = int(raw_years.strip())

    return NormalizedProfile(
        name=name,
        gender=gender,
        locations=locations,
        career_years=career_years,
    )


def extract_mentor_with_model(
    mentor_input: MentorInput,
    model_client: Any,
    *,
    max_attempts: int = 2,
    model_service_name: str = "injected-model-client",
    model_name: str | None = None,
) -> MentorResult:
    """Extract and validate one mentor without reading or writing any files."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    messages = build_extraction_messages(mentor_input)
    started = perf_counter()
    last_error: Exception | None = None
    extraction: MentorExtraction | None = None
    attempt_count = 0

    for attempt_count in range(1, max_attempts + 1):
        try:
            response = _invoke_model(model_client, messages)
            extraction = _parse_extraction(response)
            break
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

    if extraction is None:
        raise ExtractionError(
            f"single-mentor extraction failed after {max_attempts} attempt(s)"
        ) from last_error

    extraction, quality_issues = _validate_extraction_evidence(
        extraction,
        mentor_input.original_fields,
    )
    extraction = _normalize_and_guard(extraction, quality_issues)
    latency_ms = max(0, int((perf_counter() - started) * 1000))

    return MentorResult(
        **extraction.model_dump(),
        schema_version="1.0",
        prompt_version=PROMPT_VERSION,
        industry_taxonomy_version=INDUSTRY_TAXONOMY_VERSION,
        mentor_id=mentor_input.mentor_id,
        record_hash=mentor_input.record_hash,
        source=SourceMetadata(
            file=mentor_input.source_file,
            sheet=mentor_input.source_sheet,
            row=mentor_input.source_row,
        ),
        original_fields=mentor_input.original_fields,
        normalized_profile=_normalized_profile(mentor_input.original_fields),
        quality_issues=quality_issues,
        processing={
            "status": "success",
            "attempt_count": attempt_count,
            "processed_at": datetime.now(timezone.utc),
            "model_service_name": model_service_name,
            "model_name": model_name,
            "latency_ms": latency_ms,
        },
    )


def extract_single_mentor(
    mentor_input: MentorInput,
    model_client: Callable[[Sequence[Mapping[str, str]]], Any] | Any,
    **kwargs: Any,
) -> MentorResult:
    """Convenience alias for the public single-record extraction entry point."""

    return extract_mentor_with_model(mentor_input, model_client, **kwargs)


__all__ = [
    "ExtractionError",
    "build_extraction_messages",
    "extract_mentor_with_model",
    "extract_single_mentor",
]
