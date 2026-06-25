"""Schema tests for simple keyword extraction mode."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mentor_agent.simple_schemas import SimpleMentorExtraction, SimpleMentorResult
from tests.sample_data import VALID_MENTOR_INPUT


def test_simple_extraction_defaults_to_empty_lists() -> None:
    extraction = SimpleMentorExtraction.model_validate({})

    assert extraction.industries == []
    assert extraction.companies == []
    assert extraction.roles == []
    assert extraction.skills == []
    assert extraction.credentials == []
    assert extraction.education == []
    assert extraction.target_mentees == []
    assert extraction.highlights == []
    assert extraction.keywords == []
    assert extraction.summary is None


def test_simple_extraction_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SimpleMentorExtraction.model_validate({"skills": [], "evidence": []})


def test_simple_result_rejects_full_schema_version() -> None:
    payload = {
        "schema_version": "1.0",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": VALID_MENTOR_INPUT["mentor_id"],
        "record_hash": VALID_MENTOR_INPUT["record_hash"],
        "source": {
            "file": VALID_MENTOR_INPUT["source_file"],
            "sheet": VALID_MENTOR_INPUT["source_sheet"],
            "row": VALID_MENTOR_INPUT["source_row"],
        },
        "original_fields": VALID_MENTOR_INPUT["original_fields"],
        "extraction": {},
        "processing": {
            "status": "success",
            "attempt_count": 1,
            "processed_at": "2026-06-24T10:00:00+08:00",
            "model_service_name": "fake",
        },
    }

    with pytest.raises(ValidationError):
        SimpleMentorResult.model_validate(payload)
