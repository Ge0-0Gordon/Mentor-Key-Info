"""Summarize model-evaluation outputs without printing mentor source text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_agent.schemas import MentorResult, OrganizationRelationship


EMPLOYMENT_MARKERS = ("曾任", "历任", "任职", "就职", "曾在", "加入", "担任")
CREDENTIAL_OWNERSHIP_MARKERS = ("持有", "获得", "通过", "获评", "荣获", "取得", "获证")
CREDENTIAL_TERMS = re.compile(r"证书|认证|资格|资质|奖|PCC|ACC|MCC", re.IGNORECASE)
EDUCATION_TERMS = re.compile(r"本科|硕士|博士|大学|学院|MBA|EMBA", re.IGNORECASE)


@dataclass
class ModelMetrics:
    model_name: str
    directory: str
    success_count: int
    failed_count: int
    avg_latency_ms: float | None
    min_latency_ms: int | None
    max_latency_ms: int | None
    avg_attempt_count: float | None
    total_quality_issues: int
    invalid_evidence_count: int
    loose_evidence_match_count: int
    extracted_item_dropped_count: int
    employer_count: int
    client_count: int
    project_count: int
    partner_count: int
    unknown_count: int
    skill_count: int
    credential_count: int
    education_count: int
    output_json_avg_chars: float | None
    failed_error_types: dict[str, int]
    employer_without_marker: int
    credential_without_ownership_marker: int
    credential_name_without_credential_term: int
    retained_invalid_evidence: int
    potential_education_omission: int
    potential_credential_omission: int
    profiles_with_no_skills: int
    profiles_with_over_15_skills: int


def _read_metadata(directory: Path) -> dict[str, Any]:
    path = directory / "model_eval_metadata.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_results(directory: Path) -> tuple[list[MentorResult], list[int]]:
    path = directory / "mentor_results.jsonl"
    if not path.exists():
        return [], []
    results: list[MentorResult] = []
    lengths: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            result = MentorResult.model_validate_json(line)
        except ValidationError:
            continue
        results.append(result)
        lengths.append(len(line))
    return results, lengths


def _read_failures(directory: Path) -> list[dict[str, Any]]:
    path = directory / "failed_rows.jsonl"
    if not path.exists():
        return []
    failures = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            failures.append(payload)
    return failures


def _all_extracted_items(result: MentorResult) -> Iterable[Any]:
    yield from result.industry_tags
    yield from result.career_experiences
    yield from result.skills
    yield from result.credentials_and_awards
    yield from result.education
    yield from result.target_mentees
    yield from result.career_highlights
    if result.summary is not None:
        yield result.summary


def evaluate_directory(directory: Path) -> ModelMetrics:
    metadata = _read_metadata(directory)
    results, output_lengths = _read_results(directory)
    failures = _read_failures(directory)
    model_name = str(
        metadata.get("model_name")
        or (results[0].processing.model_name if results else None)
        or directory.name
    )

    latencies = [
        result.processing.latency_ms
        for result in results
        if result.processing.latency_ms is not None
    ]
    attempts = [result.processing.attempt_count for result in results]
    attempts.extend(
        int(failure.get("attempt_count", 0))
        for failure in failures
        if isinstance(failure.get("attempt_count"), int)
    )

    quality_codes = Counter(
        issue.code for result in results for issue in result.quality_issues
    )
    relationships = Counter(
        experience.relationship.value
        for result in results
        for experience in result.career_experiences
    )
    failed_error_types = Counter(
        str(failure.get("error_type", "unknown")) for failure in failures
    )
    startup_failure_count = int(metadata.get("startup_failure_count", 0) or 0)
    startup_error_type = metadata.get("startup_error_type")
    if startup_failure_count and startup_error_type:
        failed_error_types[str(startup_error_type)] += startup_failure_count

    employer_without_marker = 0
    credential_without_ownership_marker = 0
    credential_name_without_term = 0
    retained_invalid_evidence = 0
    potential_education_omission = 0
    potential_credential_omission = 0
    profiles_with_no_skills = 0
    profiles_with_over_15_skills = 0

    for result in results:
        for experience in result.career_experiences:
            if experience.relationship is OrganizationRelationship.EMPLOYER:
                evidence_text = " ".join(item.quote for item in experience.evidence)
                if not any(marker in evidence_text for marker in EMPLOYMENT_MARKERS):
                    employer_without_marker += 1

        for credential in result.credentials_and_awards:
            evidence_text = " ".join(item.quote for item in credential.evidence)
            if not any(
                marker in evidence_text for marker in CREDENTIAL_OWNERSHIP_MARKERS
            ):
                credential_without_ownership_marker += 1
            if not CREDENTIAL_TERMS.search(credential.raw_name):
                credential_name_without_term += 1

        for item in _all_extracted_items(result):
            retained_invalid_evidence += sum(
                1
                for evidence in item.evidence
                if getattr(evidence.match_type, "value", evidence.match_type) == "invalid"
            )

        source_text = " ".join(
            value
            for value in (
                result.original_fields.career_history,
                result.original_fields.background_experience,
            )
            if value
        )
        if EDUCATION_TERMS.search(source_text) and not result.education:
            potential_education_omission += 1
        source_mentions_credential = bool(CREDENTIAL_TERMS.search(source_text))
        only_system_building = "认证体系" in source_text and not any(
            marker in source_text for marker in CREDENTIAL_OWNERSHIP_MARKERS
        )
        if (
            source_mentions_credential
            and not only_system_building
            and not result.credentials_and_awards
        ):
            potential_credential_omission += 1
        if not result.skills:
            profiles_with_no_skills += 1
        if len(result.skills) > 15:
            profiles_with_over_15_skills += 1

    return ModelMetrics(
        model_name=model_name,
        directory=directory.name,
        success_count=len(results),
        failed_count=len(failures) + startup_failure_count,
        avg_latency_ms=mean(latencies) if latencies else None,
        min_latency_ms=min(latencies) if latencies else None,
        max_latency_ms=max(latencies) if latencies else None,
        avg_attempt_count=mean(attempts) if attempts else None,
        total_quality_issues=sum(quality_codes.values()),
        invalid_evidence_count=quality_codes["invalid_evidence"],
        loose_evidence_match_count=quality_codes["loose_evidence_match"],
        extracted_item_dropped_count=quality_codes["extracted_item_dropped"],
        employer_count=relationships["employer"],
        client_count=relationships["client"],
        project_count=relationships["project"],
        partner_count=relationships["partner"],
        unknown_count=relationships["unknown"],
        skill_count=sum(len(result.skills) for result in results),
        credential_count=sum(
            len(result.credentials_and_awards) for result in results
        ),
        education_count=sum(len(result.education) for result in results),
        output_json_avg_chars=mean(output_lengths) if output_lengths else None,
        failed_error_types=dict(sorted(failed_error_types.items())),
        employer_without_marker=employer_without_marker,
        credential_without_ownership_marker=credential_without_ownership_marker,
        credential_name_without_credential_term=credential_name_without_term,
        retained_invalid_evidence=retained_invalid_evidence,
        potential_education_omission=potential_education_omission,
        potential_credential_omission=potential_credential_omission,
        profiles_with_no_skills=profiles_with_no_skills,
        profiles_with_over_15_skills=profiles_with_over_15_skills,
    )


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def render_markdown(metrics: list[ModelMetrics]) -> str:
    lines = [
        "| model_name | success | failed | avg_latency_ms | min | max | avg_attempts | quality_issues | invalid | loose | dropped | employer | client | project | partner | unknown | skills | credentials | education | avg_json_chars | failed error types |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in metrics:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.model_name,
                    str(item.success_count),
                    str(item.failed_count),
                    _format_number(item.avg_latency_ms),
                    _format_number(item.min_latency_ms),
                    _format_number(item.max_latency_ms),
                    _format_number(item.avg_attempt_count),
                    str(item.total_quality_issues),
                    str(item.invalid_evidence_count),
                    str(item.loose_evidence_match_count),
                    str(item.extracted_item_dropped_count),
                    str(item.employer_count),
                    str(item.client_count),
                    str(item.project_count),
                    str(item.partner_count),
                    str(item.unknown_count),
                    str(item.skill_count),
                    str(item.credential_count),
                    str(item.education_count),
                    _format_number(item.output_json_avg_chars),
                    json.dumps(item.failed_error_types, ensure_ascii=False),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "### Redacted heuristic quality signals",
            "",
            "| model_name | employer_without_marker | credential_without_ownership | credential_name_without_term | retained_invalid_evidence | potential_education_omission | potential_credential_omission | no_skill_profiles | over_15_skill_profiles |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in metrics:
        lines.append(
            f"| {item.model_name} | {item.employer_without_marker} | "
            f"{item.credential_without_ownership_marker} | "
            f"{item.credential_name_without_credential_term} | "
            f"{item.retained_invalid_evidence} | "
            f"{item.potential_education_omission} | "
            f"{item.potential_credential_omission} | "
            f"{item.profiles_with_no_skills} | "
            f"{item.profiles_with_over_15_skills} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize redacted mentor model-evaluation metrics."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    directories = sorted(
        path
        for path in args.root.iterdir()
        if path.is_dir() and (path / "model_eval_metadata.json").exists()
    )
    metrics = [evaluate_directory(directory) for directory in directories]
    markdown = render_markdown(metrics)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
