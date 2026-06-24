"""Read mentor source rows from Excel without modifying the workbook."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from pydantic import ValidationError

from .schemas import MentorInput, OriginalFields, QualityIssue


EXPECTED_SHEET_NAME = "服务导师"
EXPECTED_SOURCE_FIELDS = [
    "序号",
    "导师姓名",
    "性别",
    "城市",
    "职业年限",
    "可辅导学员职级",
    "行业标签",
    "从业经历",
    "背景经验",
]


class ExcelValidationError(ValueError):
    """Raised when the workbook cannot satisfy the Stage 2 source contract."""


@dataclass(frozen=True)
class SkippedRow:
    source_row: int
    reason: str


@dataclass(frozen=True)
class RowIssue:
    source_row: int
    issue: QualityIssue


@dataclass(frozen=True)
class ExcelLoadSummary:
    source_file: str
    sheet: str
    total_rows: int
    valid_mentor_count: int
    skipped_count: int
    invalid_count: int
    duplicate_id_count: int
    row_issue_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExcelLoadReport:
    inputs: list[MentorInput]
    skipped_rows: list[SkippedRow]
    row_issues: list[RowIssue]
    duplicate_ids: list[str]
    summary: ExcelLoadSummary


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_excel_value(value: Any) -> Any:
    """Convert Excel library scalars to stable Python/JSON values."""

    if _is_missing(value):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (pd.Timestamp, datetime, date, time)):
        return value.isoformat()

    item = getattr(value, "item", None)
    if callable(item):
        value = item()

    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _original_fields_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: _normalize_excel_value(row[field])
        for field in EXPECTED_SOURCE_FIELDS
    }


def canonical_original_fields_json(
    original_fields: OriginalFields | Mapping[str, Any],
) -> str:
    """Serialize only the nine original fields in a deterministic form."""

    if isinstance(original_fields, OriginalFields):
        values = original_fields.model_dump(by_alias=True)
    else:
        values = {
            field: _normalize_excel_value(original_fields.get(field))
            for field in EXPECTED_SOURCE_FIELDS
        }

    normalized = {
        field: _normalize_excel_value(values.get(field))
        for field in EXPECTED_SOURCE_FIELDS
    }
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def calculate_record_hash(
    original_fields: OriginalFields | Mapping[str, Any],
) -> str:
    canonical = canonical_original_fields_json(original_fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mentor_id(sequence_no: int | float | str) -> str:
    if isinstance(sequence_no, float) and sequence_no.is_integer():
        sequence_text = str(int(sequence_no))
    else:
        sequence_text = str(sequence_no).strip()
    return f"service_mentor:{sequence_text}"


def _suspected_column_shift(original: Mapping[str, Any]) -> bool:
    if original["导师姓名"] is not None:
        return False

    gender = original["性别"]
    city = original["城市"]
    career_history = original["从业经历"]
    return any(
        (
            isinstance(gender, str) and len(gender) > 10,
            isinstance(city, str) and len(city) > 20,
            isinstance(career_history, str) and len(career_history) > 500,
        )
    )


def _issue(
    source_row: int,
    code: str,
    severity: str,
    message: str,
) -> RowIssue:
    return RowIssue(
        source_row=source_row,
        issue=QualityIssue(
            code=code,
            severity=severity,
            message=message,
        ),
    )


def load_mentor_inputs_with_report(
    excel_path: str | Path,
    sheet_name: str = EXPECTED_SHEET_NAME,
) -> ExcelLoadReport:
    """Load valid mentor rows and return non-sensitive row diagnostics."""

    path = Path(excel_path)
    if not path.is_file():
        raise FileNotFoundError(f"Excel file does not exist: {path}")

    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        if sheet_name not in workbook.sheet_names:
            available = ", ".join(workbook.sheet_names) or "<none>"
            raise ExcelValidationError(
                f"Required sheet '{sheet_name}' was not found. "
                f"Available sheets: {available}"
            )
        frame = pd.read_excel(
            workbook,
            sheet_name=sheet_name,
            dtype=object,
            keep_default_na=False,
        )

    missing_fields = [
        field for field in EXPECTED_SOURCE_FIELDS if field not in frame.columns
    ]
    if missing_fields:
        raise ExcelValidationError(
            "Missing required source fields: " + ", ".join(missing_fields)
        )

    inputs: list[MentorInput] = []
    skipped_rows: list[SkippedRow] = []
    row_issues: list[RowIssue] = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    invalid_count = 0

    for offset, row in frame.iterrows():
        source_row = int(offset) + 2
        original = _original_fields_dict(row)
        sequence_no = original["序号"]
        other_values = [original[field] for field in EXPECTED_SOURCE_FIELDS[1:]]

        if sequence_no is None and all(value is None for value in other_values):
            skipped_rows.append(SkippedRow(source_row, "completely_empty_row"))
            continue
        if sequence_no is not None and all(value is None for value in other_values):
            skipped_rows.append(SkippedRow(source_row, "sequence_only_row"))
            continue

        if _suspected_column_shift(original):
            row_issues.append(
                _issue(
                    source_row,
                    "suspected_column_shift",
                    "warning",
                    "导师姓名为空，且相邻业务字段出现异常长文本，请人工核对列对齐。",
                )
            )

        if sequence_no is None:
            invalid_count += 1
            row_issues.append(
                _issue(
                    source_row,
                    "missing_required_source_field",
                    "error",
                    "序号为空，无法生成稳定 mentor_id；该行未构造 MentorInput。",
                )
            )
            continue

        mentor_id = _mentor_id(sequence_no)
        if mentor_id in seen_ids:
            invalid_count += 1
            if mentor_id not in duplicate_ids:
                duplicate_ids.append(mentor_id)
            row_issues.append(
                _issue(
                    source_row,
                    "duplicate_mentor_id",
                    "error",
                    "序号生成的 mentor_id 与前序行重复；该行未构造 MentorInput。",
                )
            )
            continue
        seen_ids.add(mentor_id)

        try:
            original_fields = OriginalFields.model_validate(original)
            mentor_input = MentorInput(
                task="extract_mentor_key_info",
                input_schema_version="1.0",
                mentor_id=mentor_id,
                record_hash=calculate_record_hash(original_fields),
                source_file=path.name,
                source_sheet=sheet_name,
                source_row=source_row,
                original_fields=original_fields,
            )
        except ValidationError as exc:
            invalid_count += 1
            row_issues.append(
                _issue(
                    source_row,
                    "input_schema_validation_failed",
                    "error",
                    f"该行无法通过 MentorInput 校验（{exc.error_count()} 个字段错误）。",
                )
            )
            continue

        inputs.append(mentor_input)

    summary = ExcelLoadSummary(
        source_file=path.name,
        sheet=sheet_name,
        total_rows=len(frame),
        valid_mentor_count=len(inputs),
        skipped_count=len(skipped_rows),
        invalid_count=invalid_count,
        duplicate_id_count=len(duplicate_ids),
        row_issue_count=len(row_issues),
    )
    return ExcelLoadReport(
        inputs=inputs,
        skipped_rows=skipped_rows,
        row_issues=row_issues,
        duplicate_ids=duplicate_ids,
        summary=summary,
    )


def load_mentor_inputs(
    excel_path: str | Path,
    sheet_name: str = EXPECTED_SHEET_NAME,
) -> list[MentorInput]:
    """Return only valid MentorInput objects for callers that need no report."""

    return load_mentor_inputs_with_report(excel_path, sheet_name).inputs
