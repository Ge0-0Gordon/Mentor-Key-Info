"""Stage 1 tests for mentor extraction data contracts."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from mentor_agent.prompts import (
    CONFIDENCE_RULES,
    CREDENTIAL_RULES,
    EXTRACTION_EXAMPLES,
    INDUSTRY_TAXONOMY_VERSION,
    MAPPING_STATUS_RULES,
    ORGANIZATION_RELATIONSHIP_RULES,
    PROMPT_VERSION,
    SKILL_EXTRACTION_RULES,
    SOFT_INDUSTRY_TAXONOMY,
)
from mentor_agent.schemas import (
    CareerExperience,
    Confidence,
    Evidence,
    IndustryTag,
    MappingStatus,
    MentorExtraction,
    MentorInput,
    MentorResult,
    OrganizationRelationship,
    ProcessingMetadata,
    QualityIssue,
    Skill,
)
from tests.sample_data import (
    MINIMAL_VALID_RESULT,
    VALID_MENTOR_INPUT,
    VALID_MENTOR_RESULT,
)


def test_valid_mentor_input_passes() -> None:
    mentor_input = MentorInput.model_validate(VALID_MENTOR_INPUT)

    assert mentor_input.mentor_id == "service_mentor:1"
    assert mentor_input.original_fields.mentor_name == "林清（化名）"
    dumped = mentor_input.model_dump(by_alias=True)
    assert dumped["original_fields"]["导师姓名"] == "林清（化名）"


def test_valid_mentor_result_passes_and_round_trips_json() -> None:
    result = MentorResult.model_validate(VALID_MENTOR_RESULT)
    encoded = result.model_dump_json(by_alias=True)
    decoded = MentorResult.model_validate_json(encoded)

    assert decoded.mentor_id == result.mentor_id
    assert len(decoded.career_experiences) == 5


def test_all_organization_relationships_are_covered() -> None:
    result = MentorResult.model_validate(VALID_MENTOR_RESULT)
    relationships = {item.relationship.value for item in result.career_experiences}

    assert relationships == {
        "employer",
        "client",
        "project",
        "partner",
        "unknown",
    }


@pytest.mark.parametrize("confidence", ["high", "medium", "low"])
def test_valid_confidence_values_pass(confidence: str) -> None:
    payload = deepcopy(VALID_MENTOR_RESULT["industry_tags"][0])
    payload["confidence"] = confidence

    assert IndustryTag.model_validate(payload).confidence == Confidence(confidence)


def test_invalid_confidence_is_rejected() -> None:
    payload = deepcopy(VALID_MENTOR_RESULT)
    payload["industry_tags"][0]["confidence"] = "certain"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)


@pytest.mark.parametrize("status", ["mapped", "unmapped", "ambiguous"])
def test_valid_mapping_status_values_pass(status: str) -> None:
    payload = deepcopy(VALID_MENTOR_RESULT["skills"][0])
    payload["mapping_status"] = status

    assert Skill.model_validate(payload).mapping_status == MappingStatus(status)


def test_invalid_mapping_status_is_rejected() -> None:
    payload = deepcopy(VALID_MENTOR_RESULT)
    payload["skills"][0]["mapping_status"] = "guessed"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)


def test_invalid_relationship_is_rejected() -> None:
    payload = deepcopy(VALID_MENTOR_RESULT)
    payload["career_experiences"][0]["relationship"] = "vendor"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)


@pytest.mark.parametrize(
    ("target", "extra_key"),
    [
        ("root", "unexpected_root_field"),
        ("industry", "unexpected_industry_field"),
    ],
)
def test_extra_fields_are_rejected(target: str, extra_key: str) -> None:
    payload = deepcopy(VALID_MENTOR_RESULT)
    if target == "root":
        payload[extra_key] = "not allowed"
    else:
        payload["industry_tags"][0][extra_key] = "not allowed"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)


def test_optional_complex_fields_can_be_omitted() -> None:
    result = MentorResult.model_validate(MINIMAL_VALID_RESULT)
    career = CareerExperience.model_validate({
        "raw_name": "匿名组织",
        "normalized_name": None,
        "mapping_status": "unmapped",
        "relationship": "unknown",
        "employment_status": "unknown",
        "evidence": [{"source_field": "从业经历", "quote": "匿名组织"}],
        "confidence": "low",
    })

    assert result.summary is None
    assert career.raw_title is None
    assert career.time_period_raw is None


def test_list_fields_default_to_empty_and_are_not_shared() -> None:
    first = MentorExtraction.model_validate({})
    second = MentorExtraction.model_validate({})

    first.skills.append(Skill.model_validate(VALID_MENTOR_RESULT["skills"][0]))

    assert second.skills == []
    assert second.industry_tags == []
    assert second.career_experiences == []
    assert second.credentials_and_awards == []
    assert second.education == []
    assert second.target_mentees == []
    assert second.career_highlights == []


def test_industry_taxonomy_is_soft_and_outside_value_passes() -> None:
    outside_taxonomy = {
        "raw_industry": "深海机器人服务",
        "normalized_industry": "深海机器人服务",
        "industry_category": "深海产业",
        "mapping_status": "unmapped",
        "evidence": [{"source_field": "行业标签", "quote": "深海机器人服务"}],
        "confidence": "high",
    }

    item = IndustryTag.model_validate(outside_taxonomy)

    assert item.industry_category not in SOFT_INDUSTRY_TAXONOMY
    assert item.mapping_status is MappingStatus.UNMAPPED


def test_skill_raw_value_is_not_limited_to_a_vocabulary() -> None:
    free_form_skill = {
        "raw_skill": "跨星际团队职业叙事设计",
        "normalized_skill": None,
        "mapping_status": "unmapped",
        "evidence": [
            {"source_field": "背景经验", "quote": "跨星际团队职业叙事设计"}
        ],
        "confidence": "medium",
    }

    item = Skill.model_validate(free_form_skill)

    assert item.raw_skill == "跨星际团队职业叙事设计"
    assert item.normalized_skill is None


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_quality_issue_supports_warning_and_error(severity: str) -> None:
    issue = QualityIssue.model_validate({
        "code": "synthetic_issue",
        "severity": severity,
        "message": "匿名测试问题。",
    })

    assert issue.severity.value == severity


def test_invalid_evidence_source_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate({
            "source_field": "个人手机号",
            "quote": "00000000",
        })


@pytest.mark.parametrize(
    ("model", "payload", "missing_field"),
    [
        (IndustryTag, VALID_MENTOR_RESULT["industry_tags"][0], "normalized_industry"),
        (Skill, VALID_MENTOR_RESULT["skills"][0], "normalized_skill"),
        (
            CareerExperience,
            VALID_MENTOR_RESULT["career_experiences"][0],
            "normalized_name",
        ),
    ],
)
def test_core_raw_normalized_fields_are_required(
    model: type, payload: dict, missing_field: str
) -> None:
    invalid = deepcopy(payload)
    invalid.pop(missing_field)

    with pytest.raises(ValidationError):
        model.model_validate(invalid)


@pytest.mark.parametrize(
    "secret_field",
    ["access_key", "api_key", "Authorization", ".env"],
)
def test_processing_metadata_rejects_secret_fields(secret_field: str) -> None:
    payload = deepcopy(VALID_MENTOR_RESULT["processing"])
    payload[secret_field] = "secret-value"

    with pytest.raises(ValidationError):
        ProcessingMetadata.model_validate(payload)


@pytest.mark.parametrize(
    "secret_field",
    ["access_key", "api_key", "Authorization", ".env"],
)
def test_result_root_rejects_secret_fields(secret_field: str) -> None:
    payload = deepcopy(VALID_MENTOR_RESULT)
    payload[secret_field] = "secret-value"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)


def test_prompt_constants_cover_stage1_contract() -> None:
    assert PROMPT_VERSION == "mentor-extraction-v1.1"
    assert INDUSTRY_TAXONOMY_VERSION == "industry-soft-v1"
    assert len(SOFT_INDUSTRY_TAXONOMY) == 30
    assert len(set(SOFT_INDUSTRY_TAXONOMY)) == 30
    assert set(CONFIDENCE_RULES) == {"high", "medium", "low"}
    assert set(MAPPING_STATUS_RULES) == {"mapped", "unmapped", "ambiguous"}
    assert set(ORGANIZATION_RELATIONSHIP_RULES) == {
        relationship.value for relationship in OrganizationRelationship
    }
    assert CREDENTIAL_RULES
    assert SKILL_EXTRACTION_RULES


def test_prompt_examples_include_required_positive_and_negative_cases() -> None:
    represented_relationships = {
        example["expected"].get("relationship")
        for example in EXTRACTION_EXAMPLES
        if example["expected"].get("relationship") is not None
    }
    reasons = " ".join(example["reason"] for example in EXTRACTION_EXAMPLES)

    assert represented_relationships == {
        "employer",
        "client",
        "project",
        "partner",
        "unknown",
    }
    assert "不是本人获得认证" in reasons
    assert "不能仅凭职位" in reasons


def test_enum_values_match_the_public_contract() -> None:
    assert {item.value for item in Confidence} == {"high", "medium", "low"}
    assert {item.value for item in MappingStatus} == {
        "mapped",
        "unmapped",
        "ambiguous",
    }
