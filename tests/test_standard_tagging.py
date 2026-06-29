"""Offline tests for tagged simple extraction and canonical sanitizing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mentor_agent.schemas import MentorInput
from mentor_agent.simple_extractor import (
    extract_simple_mentor,
    extract_simple_mentor_batch,
)
from mentor_agent.simple_prompts import (
    build_tagged_simple_extraction_messages,
)
from mentor_agent.simple_schemas import (
    SimpleMentorResult,
    TaggedPosition,
)
from mentor_agent.tag_taxonomy import load_tag_taxonomy
from tests.sample_data import VALID_MENTOR_INPUT


@dataclass
class FakeModel:
    response: Any
    calls: list[Any] = field(default_factory=list)

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return self.response


def _mentor_input(index: int = 1) -> MentorInput:
    payload = dict(VALID_MENTOR_INPUT)
    payload["mentor_id"] = f"service_mentor:{index}"
    payload["record_hash"] = str(index) * 64
    fields = dict(VALID_MENTOR_INPUT["original_fields"])
    fields["序号"] = index
    payload["original_fields"] = fields
    return MentorInput.model_validate(payload)


def _taxonomy():
    return load_tag_taxonomy(Path("configs/职位类型_2.txt"))


def test_tagged_prompt_contains_closed_candidates_and_omits_review_fields() -> None:
    messages = build_tagged_simple_extraction_messages(
        _mentor_input(),
        _taxonomy(),
    )
    payload = json.loads(messages[-1]["content"])

    assert "人工智能" in payload["position_tag_candidates"]
    assert "AI/互联网/IT" in payload["industry_tag_candidates"]
    assert "互联网/AI" not in payload["position_tag_candidates"]
    assert "review_required" not in payload["output_template"]
    assert "review_reasons" not in payload["output_template"]


def test_tagged_result_metadata_and_canonical_sanitize() -> None:
    model = FakeModel(
        {
            "industry_tags": [
                {
                    "tag": "AI/互联网/IT",
                    "confidence": 0.95,
                    "evidence": "互联网",
                },
                {
                    "tag": "不存在行业",
                    "confidence": 0.9,
                    "evidence": "海洋科技",
                },
                {
                    "tag": "金融",
                    "confidence": 0.9,
                    "evidence": "",
                },
            ],
            "position_tags": [
                {
                    "tag": "人力资源",
                    "relation_type": "firsthand_role",
                    "confidence": 0.96,
                    "raw_keywords": ["人才发展"],
                    "evidence": "人才发展经理",
                },
                {
                    "tag": "人工智能",
                    "relation_type": "recruited_or_evaluated",
                    "confidence": 0.65,
                    "raw_keywords": ["招聘"],
                    "evidence": "招聘咨询服务",
                },
                {
                    "tag": "产品经理",
                    "relation_type": "invalid",
                    "confidence": 0.8,
                    "raw_keywords": [],
                    "evidence": "职业路径设计",
                },
            ],
            "company_tags": [
                {
                    "company_name": "星河网络有限公司",
                    "company_type": "互联网公司",
                    "industry_tag": "AI/互联网/IT",
                    "confidence": 0.9,
                    "evidence": "星河网络有限公司",
                }
            ],
            "raw_keywords": ["HR", "招聘"],
            "review_required": False,
            "review_reasons": ["model supplied reason"],
        }
    )

    result = extract_simple_mentor(
        _mentor_input(),
        model,
        taxonomy=_taxonomy(),
    )

    assert isinstance(result, SimpleMentorResult)
    assert result.prompt_version == "mentor-simple-tagged-v1"
    assert result.standard_tags_enabled is True
    assert result.taxonomy_hash == _taxonomy().taxonomy_hash
    assert [item.tag for item in result.extraction.industry_tags] == [
        "AI/互联网/IT"
    ]
    assert [item.tag for item in result.extraction.position_tags] == [
        "人力资源",
        "人工智能",
    ]
    assert result.extraction.position_tags[1].relation_type.value == (
        "recruited_or_evaluated"
    )
    assert result.extraction.company_tags[0].company_name == "星河网络有限公司"
    assert result.extraction.review_required is True
    assert "model supplied reason" not in result.extraction.review_reasons
    assert any(
        "tag_not_in_taxonomy" in reason
        for reason in result.extraction.review_reasons
    )
    assert any(
        "evidence_empty" in reason for reason in result.extraction.review_reasons
    )
    assert any(
        "invalid_relation_type" in reason
        for reason in result.extraction.review_reasons
    )
    assert any(
        "confidence_below_threshold" in reason
        for reason in result.extraction.review_reasons
    )


def test_evidence_from_disallowed_original_field_is_removed() -> None:
    model = FakeModel(
        {
            "industry_tags": [
                {
                    "tag": "AI/互联网/IT",
                    "confidence": 0.9,
                    "evidence": "杭州",
                }
            ]
        }
    )

    result = extract_simple_mentor(
        _mentor_input(),
        model,
        taxonomy=_taxonomy(),
    )

    assert result.extraction.industry_tags == []
    assert result.extraction.review_required is True
    assert "evidence_not_found_in_source" in result.extraction.review_reasons[0]


def test_batch_validates_evidence_against_each_mentor() -> None:
    first = _mentor_input(1)
    second_payload = _mentor_input(2).model_dump(by_alias=True)
    second_payload["original_fields"]["从业经历"] = "曾任另一家公司运营负责人。"
    second = MentorInput.model_validate(second_payload)
    response = {
        "results": [
            {
                "mentor_id": mentor_input.mentor_id,
                "extraction": {
                    "position_tags": [
                        {
                            "tag": "人力资源",
                            "relation_type": "firsthand_role",
                            "confidence": 0.9,
                            "raw_keywords": ["人才发展"],
                            "evidence": "人才发展经理",
                        }
                    ]
                },
            }
            for mentor_input in (first, second)
        ]
    }

    results = extract_simple_mentor_batch(
        [first, second],
        FakeModel(response),
        taxonomy=_taxonomy(),
    )

    assert len(results[0].extraction.position_tags) == 1
    assert results[1].extraction.position_tags == []
    assert results[1].extraction.review_required is True


def test_relation_type_schema_is_closed() -> None:
    with pytest.raises(ValidationError):
        TaggedPosition.model_validate(
            {
                "tag": "人工智能",
                "relation_type": "worked_nearby",
                "confidence": 0.9,
                "raw_keywords": [],
                "evidence": "算法团队",
            }
        )
