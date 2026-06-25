"""Offline tests for simple single-mentor extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from mentor_agent.extractor import ExtractionError, build_extraction_messages
from mentor_agent.schemas import MentorInput
from mentor_agent.simple_extractor import (
    extract_simple_mentor,
    extract_simple_mentor_batch,
)
from mentor_agent.simple_prompts import build_simple_extraction_messages
from mentor_agent.simple_schemas import MAX_ITEMS_PER_CATEGORY, SimpleMentorResult
from tests.sample_data import VALID_MENTOR_INPUT


@dataclass
class FakeModel:
    response: Any
    calls: list[Any] = field(default_factory=list)

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return self.response


def _mentor_input() -> MentorInput:
    return MentorInput.model_validate(VALID_MENTOR_INPUT)


def _mentor_input_with_id(index: int) -> MentorInput:
    payload = dict(VALID_MENTOR_INPUT)
    payload["mentor_id"] = f"service_mentor:{index}"
    payload["record_hash"] = f"{index}" * 64
    fields = dict(VALID_MENTOR_INPUT["original_fields"])
    fields[next(iter(fields))] = index
    payload["original_fields"] = fields
    return MentorInput.model_validate(payload)


def test_fake_model_simple_json_returns_simple_result_without_evidence() -> None:
    response = {
        "industries": ["互联网"],
        "companies": ["匿名公司"],
        "skills": ["简历优化"],
        "summary": "具备职业辅导经验。",
    }
    model = FakeModel(response)

    result = extract_simple_mentor(
        _mentor_input(),
        model,
        model_service_name="fake-service",
        model_name="fake-model",
    )

    assert isinstance(result, SimpleMentorResult)
    assert result.extraction.skills == ["简历优化"]
    assert result.extraction.summary == "具备职业辅导经验。"
    assert result.processing.model_service_name == "fake-service"
    assert len(model.calls) == 1
    assert "evidence" not in result.model_dump()


def test_simple_extractor_cleans_duplicates_empty_values_and_long_arrays() -> None:
    skills = ["  简历优化  ", "", "简历优化", "面试辅导"] + [
        f"技能{i}" for i in range(30)
    ]
    model = FakeModel(json.dumps({"skills": skills}, ensure_ascii=False))

    result = extract_simple_mentor(_mentor_input(), model)

    assert result.extraction.skills[:2] == ["简历优化", "面试辅导"]
    assert len(result.extraction.skills) == MAX_ITEMS_PER_CATEGORY
    assert "" not in result.extraction.skills


def test_simple_extractor_truncates_summary_before_validation() -> None:
    model = FakeModel({"summary": "很长" * 100})

    result = extract_simple_mentor(_mentor_input(), model)

    assert result.extraction.summary is not None
    assert len(result.extraction.summary) <= 120


def test_simple_extractor_rejects_extra_fields() -> None:
    model = FakeModel({"skills": [], "evidence": []})

    with pytest.raises(ExtractionError):
        extract_simple_mentor(_mentor_input(), model)


def test_invalid_json_raises_extraction_error() -> None:
    model = FakeModel("not-json")

    with pytest.raises(ExtractionError):
        extract_simple_mentor(_mentor_input(), model)


def test_simple_prompt_is_shorter_than_full_prompt() -> None:
    mentor_input = _mentor_input()
    simple_messages = build_simple_extraction_messages(mentor_input)
    full_messages = build_extraction_messages(mentor_input)
    simple_length = sum(len(message["content"]) for message in simple_messages)
    full_length = sum(len(message["content"]) for message in full_messages)

    assert simple_length < full_length
    assert "model_json_schema" not in simple_messages[-1]["content"]


def test_simple_batch_fake_model_returns_three_results() -> None:
    mentor_inputs = [_mentor_input_with_id(index) for index in range(1, 4)]
    model = FakeModel(
        {
            "results": [
                {
                    "mentor_id": mentor_input.mentor_id,
                    "extraction": {
                        "skills": ["  简历优化  ", "简历优化", ""],
                        "keywords": ["关键词"],
                    },
                }
                for mentor_input in mentor_inputs
            ]
        }
    )

    results = extract_simple_mentor_batch(
        mentor_inputs,
        model,
        model_service_name="fake-service",
        model_name="fake-model",
    )

    assert [result.mentor_id for result in results] == [
        "service_mentor:1",
        "service_mentor:2",
        "service_mentor:3",
    ]
    assert all(result.extraction.skills == ["简历优化"] for result in results)
    assert all(result.processing.attempt_count == 1 for result in results)
    assert len(model.calls) == 1


def test_simple_batch_missing_mentor_id_fails() -> None:
    mentor_inputs = [_mentor_input_with_id(index) for index in range(1, 4)]
    model = FakeModel(
        {
            "results": [
                {"mentor_id": "service_mentor:1", "extraction": {}},
                {"mentor_id": "service_mentor:2", "extraction": {}},
            ]
        }
    )

    with pytest.raises(ExtractionError):
        extract_simple_mentor_batch(mentor_inputs, model)


def test_simple_batch_extra_mentor_id_fails() -> None:
    mentor_inputs = [_mentor_input_with_id(index) for index in range(1, 3)]
    model = FakeModel(
        {
            "results": [
                {"mentor_id": "service_mentor:1", "extraction": {}},
                {"mentor_id": "service_mentor:2", "extraction": {}},
                {"mentor_id": "service_mentor:extra", "extraction": {}},
            ]
        }
    )

    with pytest.raises(ExtractionError):
        extract_simple_mentor_batch(mentor_inputs, model)


def test_simple_batch_mismatched_mentor_id_fails() -> None:
    mentor_inputs = [_mentor_input_with_id(index) for index in range(1, 3)]
    model = FakeModel(
        {
            "results": [
                {"mentor_id": "service_mentor:1", "extraction": {}},
                {"mentor_id": "service_mentor:wrong", "extraction": {}},
            ]
        }
    )

    with pytest.raises(ExtractionError):
        extract_simple_mentor_batch(mentor_inputs, model)
