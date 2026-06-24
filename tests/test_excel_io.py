"""Stage 2 tests for deterministic mentor Excel loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mentor_agent.excel_io import (
    EXPECTED_SHEET_NAME,
    EXPECTED_SOURCE_FIELDS,
    ExcelValidationError,
    calculate_record_hash,
    load_mentor_inputs,
    load_mentor_inputs_with_report,
)
from mentor_agent.schemas import MentorInput


def _mentor_row(sequence_no: object = 1) -> dict[str, object]:
    return {
        "序号": sequence_no,
        "导师姓名": "测试导师",
        "性别": "女",
        "城市": "杭州",
        "职业年限": 12,
        "可辅导学员职级": "P5/P6；管理者",
        "行业标签": "软件、咨询",
        "从业经历": "第一行经历\n第二行经历；保留分号",
        "背景经验": "擅长职业规划|面试辅导",
    }


def _write_excel(
    path: Path,
    rows: list[dict[str, object]],
    *,
    sheet_name: str = EXPECTED_SHEET_NAME,
    columns: list[str] | None = None,
) -> None:
    pd.DataFrame(rows, columns=columns).to_excel(
        path,
        sheet_name=sheet_name,
        index=False,
        engine="openpyxl",
    )


def test_normal_row_becomes_valid_mentor_input(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.xlsx"
    _write_excel(path, [_mentor_row()])

    inputs = load_mentor_inputs(path)

    assert len(inputs) == 1
    mentor_input = inputs[0]
    assert isinstance(mentor_input, MentorInput)
    assert mentor_input.task == "extract_mentor_key_info"
    assert mentor_input.input_schema_version == "1.0"
    assert mentor_input.mentor_id == "service_mentor:1"
    assert mentor_input.source_row == 2


def test_missing_sheet_raises_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "wrong_sheet.xlsx"
    _write_excel(path, [_mentor_row()], sheet_name="其他")

    with pytest.raises(ExcelValidationError, match="服务导师"):
        load_mentor_inputs(path)


def test_missing_required_field_raises_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "missing_field.xlsx"
    columns = [field for field in EXPECTED_SOURCE_FIELDS if field != "背景经验"]
    _write_excel(path, [_mentor_row()], columns=columns)

    with pytest.raises(ExcelValidationError, match="背景经验"):
        load_mentor_inputs(path)


def test_extra_fields_do_not_enter_original_fields(tmp_path: Path) -> None:
    path = tmp_path / "extra_field.xlsx"
    row = _mentor_row()
    row["index"] = 99
    _write_excel(path, [row])

    dumped = load_mentor_inputs(path)[0].original_fields.model_dump(by_alias=True)

    assert set(dumped) == set(EXPECTED_SOURCE_FIELDS)
    assert "index" not in dumped


def test_empty_and_sequence_only_rows_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "blank_rows.xlsx"
    rows = [
        _mentor_row(1),
        {field: None for field in EXPECTED_SOURCE_FIELDS},
        {"序号": 2},
        _mentor_row(3),
    ]
    _write_excel(path, rows, columns=EXPECTED_SOURCE_FIELDS)

    report = load_mentor_inputs_with_report(path)

    assert len(report.inputs) == 2
    assert [item.reason for item in report.skipped_rows] == [
        "completely_empty_row",
        "sequence_only_row",
    ]
    assert [item.source_row for item in report.skipped_rows] == [3, 4]


def test_missing_sequence_row_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "missing_sequence.xlsx"
    row = _mentor_row(None)
    _write_excel(path, [row])

    report = load_mentor_inputs_with_report(path)

    assert report.inputs == []
    assert report.summary.invalid_count == 1
    assert report.row_issues[0].issue.code == "missing_required_source_field"


def test_duplicate_sequence_is_detected_and_not_loaded_twice(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.xlsx"
    _write_excel(path, [_mentor_row(7), _mentor_row(7)])

    report = load_mentor_inputs_with_report(path)

    assert len(report.inputs) == 1
    assert report.duplicate_ids == ["service_mentor:7"]
    assert report.summary.duplicate_id_count == 1
    assert any(
        item.issue.code == "duplicate_mentor_id" for item in report.row_issues
    )


def test_record_hash_is_stable_and_changes_with_original_field() -> None:
    original = _mentor_row()

    first = calculate_record_hash(original)
    second = calculate_record_hash(dict(original))
    changed = dict(original)
    changed["城市"] = "上海"

    assert first == second
    assert first != calculate_record_hash(changed)
    assert len(first) == 64


def test_source_file_is_only_the_filename(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    path = nested / "mentors.xlsx"
    _write_excel(path, [_mentor_row()])

    mentor_input = load_mentor_inputs(path)[0]

    assert mentor_input.source_file == "mentors.xlsx"
    assert str(nested) not in mentor_input.source_file


def test_original_text_preserves_newlines_and_separators(tmp_path: Path) -> None:
    path = tmp_path / "text.xlsx"
    row = _mentor_row()
    row["从业经历"] = "经历 A\n经历 B；经历 C|经历 D"
    _write_excel(path, [row])

    original = load_mentor_inputs(path)[0].original_fields

    assert original.career_history == "经历 A\n经历 B；经历 C|经历 D"


def test_numeric_float_is_not_converted_to_text(tmp_path: Path) -> None:
    path = tmp_path / "numeric.xlsx"
    row = _mentor_row(1.5)
    row["职业年限"] = 24.5
    _write_excel(path, [row])

    original = load_mentor_inputs(path)[0].original_fields

    assert original.sequence_no == 1.5
    assert original.career_years == 24.5
    assert not isinstance(original.career_years, str)


def test_suspected_column_shift_adds_warning(tmp_path: Path) -> None:
    path = tmp_path / "shift.xlsx"
    row = _mentor_row()
    row["导师姓名"] = None
    row["性别"] = "这是一段明显不应出现在性别字段中的长文本"
    _write_excel(path, [row])

    report = load_mentor_inputs_with_report(path)

    assert len(report.inputs) == 1
    assert any(
        item.issue.code == "suspected_column_shift"
        and item.issue.severity.value == "warning"
        for item in report.row_issues
    )


REAL_EXCEL_PATH = Path(__file__).resolve().parents[1] / "职优越导师资料（最新）.xlsx"


@pytest.mark.skipif(not REAL_EXCEL_PATH.exists(), reason="real mentor Excel is absent")
def test_real_excel_stage2_smoke() -> None:
    report = load_mentor_inputs_with_report(REAL_EXCEL_PATH)

    assert report.summary.sheet == EXPECTED_SHEET_NAME
    assert report.summary.valid_mentor_count == 121
    assert report.summary.skipped_count > 0
    assert report.summary.duplicate_id_count == 0
    assert len({item.mentor_id for item in report.inputs}) == 121
    for item in report.inputs:
        MentorInput.model_validate(item.model_dump())
        assert item.record_hash
        assert item.record_hash == calculate_record_hash(item.original_fields)
