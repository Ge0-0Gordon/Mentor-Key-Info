"""Offline tests for the injectable single-mentor extraction pipeline."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from mentor_agent.extractor import (
    ExtractionError,
    build_extraction_messages,
    extract_mentor_with_model,
)
from mentor_agent.schemas import (
    CredentialStatus,
    EvidenceMatchType,
    MappingStatus,
    MentorInput,
    MentorResult,
    OrganizationRelationship,
)


class FakeModel:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]]) -> Any:
        self.calls.append(messages)
        response = self.responses[len(self.calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response


def _mentor_input() -> MentorInput:
    return MentorInput.model_validate(
        {
            "task": "extract_mentor_key_info",
            "input_schema_version": "1.0",
            "mentor_id": "service_mentor:1",
            "record_hash": "a" * 64,
            "source_file": "synthetic.xlsx",
            "source_sheet": "服务导师",
            "source_row": 2,
            "original_fields": {
                "序号": 1,
                "导师姓名": "测试导师",
                "性别": "女",
                "城市": "杭州",
                "职业年限": 12,
                "可辅导学员职级": "P5-P7",
                "行业标签": "深海机器人服务",
                "从业经历": (
                    "曾任星河科技人才发展经理。"
                    "为云帆零售提供招聘咨询服务。"
                    "参与海岸研究院人才盘点项目。"
                ),
                "背景经验": (
                    "擅长简历优化，面试辅导。"
                    "主导公司面试官认证体系建设。"
                    "目前为准 PCC 教练。"
                ),
            },
        }
    )


def _skill(quote: str, *, confidence: str = "high") -> dict[str, Any]:
    return {
        "raw_skill": "跨星际团队职业叙事设计",
        "normalized_skill": None,
        "mapping_status": "unmapped",
        "evidence": [{"source_field": "背景经验", "quote": quote}],
        "confidence": confidence,
    }


def _career(raw_name: str, quote: str) -> dict[str, Any]:
    return {
        "raw_name": raw_name,
        "normalized_name": None,
        "mapping_status": "unmapped",
        "relationship": "employer",
        "employment_status": "unknown",
        "evidence": [{"source_field": "从业经历", "quote": quote}],
        "confidence": "high",
    }


def _credential(raw_name: str, quote: str, status: str = "held") -> dict[str, Any]:
    return {
        "raw_name": raw_name,
        "normalized_name": None,
        "mapping_status": "unmapped",
        "category": "professional_certification",
        "credential_status": status,
        "evidence": [{"source_field": "背景经验", "quote": quote}],
        "confidence": "high",
    }


def test_prompt_requires_json_and_puts_mentor_input_in_last_user_message() -> None:
    messages = build_extraction_messages(_mentor_input())
    user_payload = json.loads(messages[-1]["content"])

    assert messages[-1]["role"] == "user"
    assert user_payload["mentor_input"]["mentor_id"] == "service_mentor:1"
    assert "只输出一个合法 JSON" in messages[0]["content"]


def test_strict_evidence_is_kept_without_warning() -> None:
    model = FakeModel([{"skills": [_skill("擅长简历优化，面试辅导")] }])

    result = extract_mentor_with_model(_mentor_input(), model)

    assert len(result.skills) == 1
    assert result.skills[0].evidence[0].match_type is EvidenceMatchType.STRICT
    assert result.quality_issues == []


def test_loose_evidence_is_kept_and_adds_warning() -> None:
    model = FakeModel([{"skills": [_skill("擅长 简历优化; 面试辅导")] }])

    result = extract_mentor_with_model(_mentor_input(), model)

    assert len(result.skills) == 1
    assert result.skills[0].evidence[0].match_type is EvidenceMatchType.LOOSE
    assert "loose_evidence_match" in {issue.code for issue in result.quality_issues}


def test_invalid_evidence_drops_item_and_adds_quality_issues() -> None:
    model = FakeModel([{"skills": [_skill("原文不存在的技能证据")] }])

    result = extract_mentor_with_model(_mentor_input(), model)

    assert result.skills == []
    assert {issue.code for issue in result.quality_issues} == {
        "invalid_evidence",
        "extracted_item_dropped",
    }


def test_invalid_json_retries_then_succeeds() -> None:
    model = FakeModel(["not-json", {}])

    result = extract_mentor_with_model(_mentor_input(), model, max_attempts=2)

    assert len(model.calls) == 2
    assert result.processing.attempt_count == 2


def test_invalid_json_fails_loudly_after_retry_limit() -> None:
    model = FakeModel(["not-json", "still-not-json"])

    with pytest.raises(ExtractionError):
        extract_mentor_with_model(_mentor_input(), model, max_attempts=2)

    assert len(model.calls) == 2


def test_invalid_confidence_is_rejected_by_pydantic() -> None:
    model = FakeModel([{"skills": [_skill("擅长简历优化", confidence="certain")] }])

    with pytest.raises(ExtractionError) as exc_info:
        extract_mentor_with_model(_mentor_input(), model, max_attempts=1)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_service_and_project_relationships_are_not_employer() -> None:
    payload = {
        "career_experiences": [
            _career("云帆零售", "为云帆零售提供招聘咨询服务"),
            _career("海岸研究院", "参与海岸研究院人才盘点项目"),
        ]
    }

    result = extract_mentor_with_model(_mentor_input(), FakeModel([payload]))

    assert [item.relationship for item in result.career_experiences] == [
        OrganizationRelationship.CLIENT,
        OrganizationRelationship.PROJECT,
    ]
    assert all(
        item.relationship is not OrganizationRelationship.EMPLOYER
        for item in result.career_experiences
    )


def test_explicit_employment_relationship_remains_employer() -> None:
    payload = {
        "career_experiences": [
            _career("星河科技", "曾任星河科技人才发展经理")
        ]
    }

    result = extract_mentor_with_model(_mentor_input(), FakeModel([payload]))

    assert result.career_experiences[0].relationship is OrganizationRelationship.EMPLOYER


def test_building_certification_system_does_not_become_personal_credential() -> None:
    payload = {
        "credentials_and_awards": [
            _credential("面试官认证", "主导公司面试官认证体系建设")
        ]
    }

    result = extract_mentor_with_model(_mentor_input(), FakeModel([payload]))

    assert result.credentials_and_awards == []
    assert "credential_not_personally_held" in {
        issue.code for issue in result.quality_issues
    }


def test_candidate_credential_cannot_remain_held() -> None:
    payload = {
        "credentials_and_awards": [
            _credential("PCC", "目前为准 PCC 教练", status="held")
        ]
    }

    result = extract_mentor_with_model(_mentor_input(), FakeModel([payload]))

    assert result.credentials_and_awards[0].credential_status is CredentialStatus.CANDIDATE


def test_outside_taxonomy_industry_and_free_skill_are_retained() -> None:
    payload = {
        "industry_tags": [
            {
                "raw_industry": "深海机器人服务",
                "normalized_industry": "其他",
                "industry_category": "其他",
                "mapping_status": "mapped",
                "evidence": [
                    {"source_field": "行业标签", "quote": "深海机器人服务"}
                ],
                "confidence": "high",
            }
        ],
        "skills": [_skill("擅长简历优化")],
    }

    result = extract_mentor_with_model(_mentor_input(), FakeModel([payload]))

    assert result.industry_tags[0].normalized_industry == "深海机器人服务"
    assert result.industry_tags[0].mapping_status is MappingStatus.UNMAPPED
    assert result.skills[0].raw_skill == "跨星际团队职业叙事设计"
    assert result.skills[0].mapping_status is MappingStatus.UNMAPPED


def test_model_output_cannot_store_sensitive_extra_fields() -> None:
    payload = {"AccessKey": "should-not-be-stored"}

    with pytest.raises(ExtractionError) as exc_info:
        extract_mentor_with_model(_mentor_input(), FakeModel([payload]), max_attempts=1)

    assert isinstance(exc_info.value.__cause__, ValidationError)


@pytest.mark.parametrize("secret_field", ["AccessKey", "API Key", "Authorization", ".env"])
def test_mentor_result_rejects_sensitive_extra_fields(secret_field: str) -> None:
    result = extract_mentor_with_model(_mentor_input(), FakeModel([{}]))
    payload = deepcopy(result.model_dump())
    payload[secret_field] = "secret"

    with pytest.raises(ValidationError):
        MentorResult.model_validate(payload)
