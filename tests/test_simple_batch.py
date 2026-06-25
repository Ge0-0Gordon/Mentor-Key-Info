"""Batch tests for simple mode and mode mismatch handling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from batch_extract import (
    FAILED_ROWS_NAME,
    FINAL_RESULTS_NAME,
    REVIEW_EXCEL_NAME,
    SIMPLE_REVIEW_SHEETS,
    SUCCESS_CHECKPOINT_RELATIVE,
    BatchConfig,
    run_batch,
)
from mentor_agent.schemas import MentorInput
from mentor_agent.simple_schemas import SimpleMentorBatchResult, SimpleMentorResult
from tests.test_batch_extract import (
    FakeResponse,
    FakeSession,
    _mentor_row,
    _read_jsonl,
    _success_response,
    _write_source,
)


def _simple_result_for_input(mentor_input: MentorInput) -> SimpleMentorResult:
    original = mentor_input.original_fields
    return SimpleMentorResult.model_validate(
        {
            "schema_version": "simple-v1",
            "prompt_version": "mentor-simple-v1",
            "mentor_id": mentor_input.mentor_id,
            "record_hash": mentor_input.record_hash,
            "source": {
                "file": mentor_input.source_file,
                "sheet": mentor_input.source_sheet,
                "row": mentor_input.source_row,
            },
            "original_fields": original.model_dump(by_alias=True),
            "extraction": {
                "industries": ["software"],
                "companies": [f"anonymous-company-{original.sequence_no}"],
                "roles": ["product owner"],
                "skills": ["product planning", "career coaching"],
                "credentials": [],
                "education": [],
                "target_mentees": ["P5-P7"],
                "highlights": ["anonymous project experience"],
                "keywords": ["product", "coaching"],
                "summary": "Synthetic simple result for offline tests.",
            },
            "processing": {
                "status": "success",
                "attempt_count": 1,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "model_service_name": "fake-http",
                "model_name": "fake-simple-model",
                "latency_ms": 5,
            },
        }
    )


def _simple_success_response(request_kwargs: dict[str, Any]) -> FakeResponse:
    content = request_kwargs["json"]["messages"][0]["content"]
    mentor_input = MentorInput.model_validate_json(content)
    result = _simple_result_for_input(mentor_input)
    return FakeResponse(
        payload={
            "choices": [
                {"message": {"content": result.model_dump_json(by_alias=True)}}
            ]
        }
    )


def _simple_batch_success_response(request_kwargs: dict[str, Any]) -> FakeResponse:
    content = request_kwargs["json"]["messages"][0]["content"]
    payload = json.loads(content)
    results = [
        _simple_result_for_input(MentorInput.model_validate(record))
        for record in payload["records"]
    ]
    batch_result = SimpleMentorBatchResult(
        schema_version="simple-batch-v1",
        results=results,
    )
    return FakeResponse(
        payload={
            "choices": [
                {"message": {"content": batch_result.model_dump_json(by_alias=True)}}
            ]
        }
    )


def test_simple_mode_writes_jsonl_and_three_sheet_review_excel(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1), _mentor_row(2), _mentor_row(3)])

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=3,
            max_retries=0,
        ),
        session=FakeSession([_simple_batch_success_response]),
        printer=lambda message: None,
    )

    assert summary.success_count == 3
    checkpoint_rows = _read_jsonl(output / SUCCESS_CHECKPOINT_RELATIVE)
    final_rows = _read_jsonl(output / FINAL_RESULTS_NAME)
    assert len(checkpoint_rows) == 3
    assert len(final_rows) == 3
    SimpleMentorResult.model_validate(final_rows[0])

    workbook = load_workbook(output / REVIEW_EXCEL_NAME, read_only=True)
    assert tuple(workbook.sheetnames) == SIMPLE_REVIEW_SHEETS
    assert workbook[workbook.sheetnames[0]].max_row == 4
    assert workbook[workbook.sheetnames[1]].max_row > 3


def test_simple_resume_loads_only_simple_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1)])

    run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=1,
            max_retries=0,
            no_excel=True,
        ),
        session=FakeSession([_simple_success_response]),
        printer=lambda message: None,
    )
    session = FakeSession()
    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=1,
            resume=True,
            max_retries=0,
            no_excel=True,
        ),
        session=session,
        printer=lambda message: None,
    )

    assert summary.skipped_resume_count == 1
    assert session.calls == []


def test_batch_simple_mode_rejects_full_result(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1)])

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=1,
            max_retries=0,
            no_excel=True,
        ),
        session=FakeSession([_success_response]),
        printer=lambda message: None,
    )

    failure = _read_jsonl(output / FAILED_ROWS_NAME)[0]
    assert summary.failed_count == 1
    assert failure["error_type"] == "mentor_result_validation_failed"
    assert _read_jsonl(output / SUCCESS_CHECKPOINT_RELATIVE) == []


def test_batch_full_mode_rejects_simple_result(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1)])

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="full",
            batch_size=1,
            max_retries=0,
            no_excel=True,
        ),
        session=FakeSession([_simple_success_response]),
        printer=lambda message: None,
    )

    failure = _read_jsonl(output / FAILED_ROWS_NAME)[0]
    assert summary.failed_count == 1
    assert failure["error_type"] == "mentor_result_validation_failed"
    assert _read_jsonl(output / SUCCESS_CHECKPOINT_RELATIVE) == []


def test_full_resume_does_not_silently_load_simple_checkpoint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1)])

    run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=1,
            max_retries=0,
            no_excel=True,
        ),
        session=FakeSession([_simple_success_response]),
        printer=lambda message: None,
    )
    printed: list[str] = []
    session = FakeSession([_success_response])

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="full",
            batch_size=1,
            resume=True,
            max_retries=0,
            no_excel=True,
        ),
        session=session,
        printer=printed.append,
    )

    assert summary.skipped_resume_count == 0
    assert summary.success_count == 1
    assert len(session.calls) == 1
    assert any("mismatched full checkpoint" in message for message in printed)


def test_simple_batch_failure_falls_back_to_single_requests(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1), _mentor_row(2), _mentor_row(3)])
    session = FakeSession(
        [
            FakeResponse(payload={"choices": [{"message": {"content": "{}"}}]}),
            _simple_success_response,
            _simple_success_response,
            _simple_success_response,
        ]
    )
    printed: list[str] = []

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=3,
            max_retries=0,
            no_excel=True,
        ),
        session=session,
        printer=printed.append,
    )

    assert summary.success_count == 3
    assert summary.failed_count == 0
    assert len(session.calls) == 4
    assert any("batch fallback size=3" in message for message in printed)
    assert len(_read_jsonl(output / SUCCESS_CHECKPOINT_RELATIVE)) == 3


def test_simple_batch_resume_skips_without_http_calls(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "outputs"
    _write_source(source, [_mentor_row(1), _mentor_row(2), _mentor_row(3)])

    run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=3,
            max_retries=0,
            no_excel=True,
        ),
        session=FakeSession([_simple_batch_success_response]),
        printer=lambda message: None,
    )
    session = FakeSession()

    summary = run_batch(
        BatchConfig(
            input_path=source,
            output_dir=output,
            mode="simple",
            batch_size=3,
            resume=True,
            max_retries=0,
            no_excel=True,
        ),
        session=session,
        printer=lambda message: None,
    )

    assert summary.skipped_resume_count == 3
    assert summary.success_count == 0
    assert summary.final_result_count == 3
    assert session.calls == []
