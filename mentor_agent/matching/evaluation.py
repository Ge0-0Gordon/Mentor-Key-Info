"""Offline quality evaluation helpers for recommendation-v1.

This module intentionally does not change ranking behavior. It runs the
existing RecommendationEngine over structured StudentProfile cases and produces
weak-signal diagnostics plus optional supervised metrics when human labels are
available.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aliases import normalize_text
from .ranking_engine import RecommendationEngine
from .schemas import MatchItem, MatchResult, StudentProfile

FORBIDDEN_OUTPUT_TERMS = ["曾就职", "任职过", "供职", "前员工", "老东家"]
SCORING_FIELDS = [
    "company_match",
    "role_match",
    "skill_match",
    "industry_match",
    "stage_match",
    "years_match",
    "semantic_match",
]
REVIEW_COLUMNS = [
    "case_id",
    "rank",
    "mentor_id",
    "name",
    "final_score",
    *SCORING_FIELDS,
    "industries",
    "companies",
    "roles",
    "skills",
    "target_mentees",
    "summary",
    "auto_signal_hits",
    "human_label",
    "human_notes",
]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    description: str
    student_profile: StudentProfile
    expected_signals: dict[str, Any]
    manual_judgement: Any = None


@dataclass(frozen=True)
class GoldLabel:
    case_id: str
    good_mentor_ids: set[str]
    acceptable_mentor_ids: set[str]
    bad_mentor_ids: set[str]
    notes: str = ""

    @property
    def has_positive_labels(self) -> bool:
        return bool(self.good_mentor_ids or self.acceptable_mentor_ids)


def load_eval_cases(path: str | Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            profile_payload = dict(payload["student_profile"])
            profile_payload.setdefault("raw_query", payload.get("description") or payload["case_id"])
            cases.append(
                EvalCase(
                    case_id=str(payload["case_id"]),
                    description=str(payload.get("description") or ""),
                    student_profile=StudentProfile.model_validate(profile_payload),
                    expected_signals=dict(payload.get("expected_signals") or {}),
                    manual_judgement=payload.get("manual_judgement"),
                )
            )
    return cases


def load_gold_labels(path: str | Path | None) -> dict[str, GoldLabel]:
    if path is None:
        return {}
    labels: dict[str, GoldLabel] = {}
    gold_path = Path(path)
    if not gold_path.exists():
        return {}
    with gold_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            label = GoldLabel(
                case_id=str(payload["case_id"]),
                good_mentor_ids={str(value) for value in payload.get("good_mentor_ids", [])},
                acceptable_mentor_ids={str(value) for value in payload.get("acceptable_mentor_ids", [])},
                bad_mentor_ids={str(value) for value in payload.get("bad_mentor_ids", [])},
                notes=str(payload.get("notes") or ""),
            )
            labels[label.case_id] = label
    return labels


def _expected_terms(expected_signals: dict[str, Any]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "companies": [],
        "roles": [],
        "skills": [],
        "stage": [],
        "industries": [],
        "background": [],
    }
    for section_name in ("must_match_any", "nice_to_have"):
        section = expected_signals.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        for key, values in section.items():
            if key not in buckets:
                buckets[key] = []
            if isinstance(values, list):
                buckets[key].extend(str(value) for value in values if value)
    return buckets


def _signal_text(item: MatchItem) -> str:
    display = item.display
    debug = item.debug
    parts: list[str] = [
        display.mentor_id,
        display.name or "",
        display.city or "",
        display.summary or "",
        *display.industries,
        *display.companies,
        *display.roles,
        *display.skills,
        *display.credentials,
        *display.education,
        *display.target_mentees,
        *display.highlights,
        *display.keywords,
    ]
    for signal_list in debug.matched_signals.model_dump(mode="json").values():
        for signal in signal_list:
            parts.extend(
                str(signal.get(key) or "")
                for key in ("query_term", "matched_term", "canonical", "source_field", "match_type")
            )
    return " ".join(parts)


def _term_is_covered(term: str, items: list[MatchItem]) -> bool:
    needle = normalize_text(term)
    return bool(needle) and any(needle in normalize_text(_signal_text(item)) for item in items)


def expected_signal_coverage(
    expected_signals: dict[str, Any],
    items: list[MatchItem],
) -> dict[str, Any]:
    expected = _expected_terms(expected_signals)
    mapping = {
        "companies": "company_coverage",
        "roles": "role_coverage",
        "skills": "skill_coverage",
        "stage": "stage_coverage",
        "industries": "industry_coverage",
        "background": "background_coverage",
    }
    result: dict[str, Any] = {}
    missing: dict[str, list[str]] = {}
    coverage_values: list[float] = []
    for category, output_key in mapping.items():
        terms = expected.get(category, [])
        if not terms:
            result[output_key] = None
            continue
        missing_terms = [term for term in terms if not _term_is_covered(term, items)]
        coverage = (len(terms) - len(missing_terms)) / len(terms)
        result[output_key] = round(coverage, 4)
        coverage_values.append(coverage)
        if missing_terms:
            missing[category] = missing_terms
    result["overall_coverage"] = round(statistics.mean(coverage_values), 4) if coverage_values else None
    result["missing_expected_signals"] = missing
    return result


def _has_signal(item: MatchItem, category: str, expected_terms: list[str]) -> bool:
    matched = getattr(item.debug.matched_signals, category, [])
    if matched:
        return True
    if category == "target_mentees":
        values = item.display.target_mentees
    elif category == "industries":
        values = item.display.industries
    elif category == "companies":
        values = item.display.companies
    elif category == "roles":
        values = item.display.roles
    elif category == "skills":
        values = item.display.skills
    else:
        values = []
    text = " ".join([*values, item.display.summary or "", *item.display.keywords])
    normalized_text = normalize_text(text)
    return any(normalize_text(term) in normalized_text for term in expected_terms)


def weak_case_metrics(case: EvalCase, result: MatchResult, latency_ms: int) -> dict[str, Any]:
    top_items = result.results[: result.top_k]
    scores = [item.debug.final_score for item in top_items]
    expected = _expected_terms(case.expected_signals)
    coverage = expected_signal_coverage(case.expected_signals, top_items)
    return {
        "case_id": case.case_id,
        "description": case.description,
        "top1_score": scores[0] if scores else 0,
        "top3_avg_score": statistics.mean(scores[:3]) if scores[:3] else 0,
        "top10_avg_score": statistics.mean(scores) if scores else 0,
        "top10_min_score": min(scores) if scores else 0,
        "zero_score_count": sum(1 for score in scores if score <= 0),
        "top10_company_hit_count": sum(1 for item in top_items if _has_signal(item, "companies", expected["companies"])),
        "top10_role_hit_count": sum(1 for item in top_items if _has_signal(item, "roles", expected["roles"])),
        "top10_skill_hit_count": sum(1 for item in top_items if _has_signal(item, "skills", expected["skills"])),
        "top10_stage_hit_count": sum(1 for item in top_items if _has_signal(item, "target_mentees", expected["stage"])),
        "top10_industry_hit_count": sum(1 for item in top_items if _has_signal(item, "industries", expected["industries"])),
        "top10_expected_signal_coverage": coverage["overall_coverage"],
        "missing_expected_signals": coverage["missing_expected_signals"],
        "top10_distinct_industries": len({value for item in top_items for value in item.display.industries}),
        "top10_distinct_roles": len({value for item in top_items for value in item.display.roles}),
        "latency_ms": latency_ms,
        "coverage": coverage,
    }


def supervised_metrics(result: MatchResult, gold_label: GoldLabel | None) -> dict[str, Any]:
    if gold_label is None or not gold_label.has_positive_labels:
        return {}
    ranked_ids = [item.display.mentor_id for item in result.results[: result.top_k]]
    positive_ids = gold_label.good_mentor_ids | gold_label.acceptable_mentor_ids

    def hit_at(k: int) -> int:
        return int(any(mentor_id in positive_ids for mentor_id in ranked_ids[:k]))

    reciprocal_rank = 0.0
    for idx, mentor_id in enumerate(ranked_ids, start=1):
        if mentor_id in positive_ids:
            reciprocal_rank = 1.0 / idx
            break

    relevance = [
        2 if mentor_id in gold_label.good_mentor_ids else 1 if mentor_id in gold_label.acceptable_mentor_ids else 0
        for mentor_id in ranked_ids[:10]
    ]
    ideal_relevance = sorted(
        [2] * len(gold_label.good_mentor_ids) + [1] * len(gold_label.acceptable_mentor_ids),
        reverse=True,
    )[:10]
    return {
        "Hit@1": hit_at(1),
        "Hit@3": hit_at(3),
        "Hit@5": hit_at(5),
        "Hit@10": hit_at(10),
        "MRR": round(reciprocal_rank, 4),
        "NDCG@10": round(_ndcg(relevance, ideal_relevance), 4),
        "bad_in_top10_count": sum(1 for mentor_id in ranked_ids[:10] if mentor_id in gold_label.bad_mentor_ids),
    }


def _dcg(relevance: list[int]) -> float:
    return sum((2**rel - 1) / math.log2(idx + 2) for idx, rel in enumerate(relevance))


def _ndcg(relevance: list[int], ideal_relevance: list[int]) -> float:
    ideal = _dcg(ideal_relevance)
    return _dcg(relevance) / ideal if ideal else 0.0


def _join(values: list[str]) -> str:
    return "；".join(str(value) for value in values if value)


def _breakdown_value(item: MatchItem, field: str) -> Any:
    value = getattr(item.debug.score_breakdown, field)
    return "" if value is None else value


def _auto_signal_hits(item: MatchItem) -> str:
    signals = item.debug.matched_signals
    buckets = []
    for name in ("companies", "roles", "skills", "target_mentees", "industries", "keywords"):
        values = getattr(signals, name)
        if values:
            buckets.append(f"{name}:{len(values)}")
    return ", ".join(buckets)


def review_rows(case: EvalCase, result: MatchResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result.results[: result.top_k]:
        display = item.display
        row = {
            "case_id": case.case_id,
            "rank": display.rank,
            "mentor_id": display.mentor_id,
            "name": display.name or "",
            "final_score": item.debug.final_score,
            "industries": _join(display.industries),
            "companies": _join(display.companies),
            "roles": _join(display.roles),
            "skills": _join(display.skills),
            "target_mentees": _join(display.target_mentees),
            "summary": display.summary or "",
            "auto_signal_hits": _auto_signal_hits(item),
            "human_label": "",
            "human_notes": "",
        }
        for field in SCORING_FIELDS:
            row[field] = _breakdown_value(item, field)
        rows.append(row)
    return rows


def detail_payload(case: EvalCase, result: MatchResult, metrics: dict[str, Any], supervised: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "description": case.description,
        "student_profile": case.student_profile.model_dump(mode="json"),
        "weak_metrics": metrics,
        "supervised_metrics": supervised,
        "top_recommendations": [
            {
                "display": item.display.model_dump(mode="json"),
                "debug": {
                    "final_score": item.debug.final_score,
                    "score_breakdown": item.debug.score_breakdown.model_dump(mode="json"),
                    "matched_signals": item.debug.matched_signals.model_dump(mode="json"),
                    "possible_gap": item.debug.possible_gap,
                    "scoring_version": item.debug.scoring_version,
                },
            }
            for item in result.results[: result.top_k]
        ],
    }


def diagnose_case(metrics: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    missing = metrics.get("missing_expected_signals") or {}
    for category, values in missing.items():
        if values:
            notes.append(f"Potential alias/data gap in {category}: {', '.join(values[:5])}")
    if metrics.get("zero_score_count", 0) > 0:
        notes.append("Top10 contains zero-score mentors; manual review recommended.")
    return notes


def run_quality_evaluation(
    *,
    mentors_path: str | Path,
    cases_path: str | Path,
    aliases_path: str | Path,
    output_dir: str | Path,
    top_k: int = 10,
    semantic: str = "none",
    gold_labels_path: str | Path | None = None,
    show_debug: bool = False,
) -> dict[str, Any]:
    cases = load_eval_cases(cases_path)
    gold_labels = load_gold_labels(gold_labels_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    engine = RecommendationEngine.from_jsonl(
        mentors_path,
        aliases_path,
        semantic_mode=semantic,
        embedding_cache_path=output_path / "mentor_embeddings.json" if semantic != "none" else None,
    )

    summary_rows: list[dict[str, Any]] = []
    all_review_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    supervised_rows: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        result = engine.recommend(case.student_profile, top_k=top_k)
        latency_ms = int((time.perf_counter() - started) * 1000)
        metrics = weak_case_metrics(case, result, latency_ms)
        supervised = supervised_metrics(result, gold_labels.get(case.case_id))
        summary_row = {
            **{key: value for key, value in metrics.items() if key not in {"coverage", "missing_expected_signals"}},
            "top10_expected_signal_coverage": metrics["top10_expected_signal_coverage"],
            "missing_expected_signals_json": json.dumps(metrics["missing_expected_signals"], ensure_ascii=False),
            "notes": " | ".join(diagnose_case(metrics)),
        }
        summary_rows.append(summary_row)
        if supervised:
            supervised_rows.append({"case_id": case.case_id, **supervised})
        all_review_rows.extend(review_rows(case, result))
        details.append(detail_payload(case, result, metrics, supervised))

    sanitized_details = [_sanitize_for_output(detail) for detail in details]
    _write_csv(output_path / "recommendation_quality_summary.csv", summary_rows)
    _write_csv(output_path / "recommendation_quality_review.csv", all_review_rows, fieldnames=REVIEW_COLUMNS)
    _write_jsonl(output_path / "recommendation_quality_details.jsonl", sanitized_details)
    report = render_markdown_report(
        mentors_path=Path(mentors_path),
        cases_path=Path(cases_path),
        semantic=semantic,
        top_k=top_k,
        summary_rows=summary_rows,
        details=sanitized_details,
        supervised_rows=supervised_rows,
        show_debug=show_debug,
    )
    report_path = output_path / "recommendation_quality_report.md"
    _assert_safe_output(report)
    report_path.write_text(report, encoding="utf-8")
    return {
        "output_dir": str(output_path),
        "report_path": str(report_path),
        "case_count": len(cases),
        "avg_latency_ms": _mean([row["latency_ms"] for row in summary_rows]),
        "p95_latency_ms": _p95([row["latency_ms"] for row in summary_rows]),
        "avg_expected_signal_coverage": _mean(
            [
                row["top10_expected_signal_coverage"]
                for row in summary_rows
                if row["top10_expected_signal_coverage"] is not None
            ]
        ),
        "low_coverage_cases": [
            row["case_id"]
            for row in summary_rows
            if row["top10_expected_signal_coverage"] is not None and row["top10_expected_signal_coverage"] < 0.5
        ],
        "zero_score_cases": [row["case_id"] for row in summary_rows if row["zero_score_count"] > 0],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    safe_rows = [_sanitize_for_output(row) for row in rows]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(safe_rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            text = json.dumps(_sanitize_for_output(row), ensure_ascii=False)
            _assert_safe_output(text)
            handle.write(text + "\n")


def _mean(values: list[float | int]) -> float:
    return round(statistics.mean(values), 2) if values else 0.0


def _p95(values: list[float | int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return round(float(ordered[idx]), 2)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_markdown_report(
    *,
    mentors_path: Path,
    cases_path: Path,
    semantic: str,
    top_k: int,
    summary_rows: list[dict[str, Any]],
    details: list[dict[str, Any]],
    supervised_rows: list[dict[str, Any]],
    show_debug: bool = False,
) -> str:
    avg_latency = _mean([row["latency_ms"] for row in summary_rows])
    p95_latency = _p95([row["latency_ms"] for row in summary_rows])
    avg_top10_score = _mean([row["top10_avg_score"] for row in summary_rows])
    coverage_values = [
        row["top10_expected_signal_coverage"]
        for row in summary_rows
        if row["top10_expected_signal_coverage"] is not None
    ]
    avg_coverage = _mean(coverage_values)
    low_coverage = [
        row["case_id"]
        for row in summary_rows
        if row["top10_expected_signal_coverage"] is not None and row["top10_expected_signal_coverage"] < 0.5
    ]
    zero_score = [row["case_id"] for row in summary_rows if row["zero_score_count"] > 0]

    lines = [
        "# Recommendation Quality Evaluation Report",
        "",
        "## Summary",
        f"- mentors path: `{mentors_path}`",
        f"- cases: {len(summary_rows)} from `{cases_path}`",
        f"- semantic mode: `{semantic}`",
        f"- top_k: {top_k}",
        f"- avg latency: {avg_latency} ms",
        f"- p95 latency: {p95_latency} ms",
        f"- avg top10 score: {avg_top10_score}",
        f"- avg expected signal coverage: {avg_coverage}",
        f"- cases with zero-score in top10: {', '.join(zero_score) if zero_score else 'none'}",
        f"- cases needing review: {', '.join(low_coverage) if low_coverage else 'none'}",
        "",
        "> Weak evaluation is a debugging aid for alias, tag coverage, and scoring issues. It is not real recommendation accuracy.",
        "",
    ]
    if supervised_rows:
        lines.extend(["## Supervised Metrics", "", "| case_id | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR | NDCG@10 | bad_in_top10_count |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
        for row in supervised_rows:
            lines.append(
                f"| {row['case_id']} | {row['Hit@1']} | {row['Hit@3']} | {row['Hit@5']} | "
                f"{row['Hit@10']} | {row['MRR']} | {row['NDCG@10']} | {row['bad_in_top10_count']} |"
            )
        lines.append("")

    lines.extend(["## Case Results", ""])
    detail_by_case = {detail["case_id"]: detail for detail in details}
    for row in summary_rows:
        detail = detail_by_case[row["case_id"]]
        lines.extend(
            [
                f"### {row['case_id']}: {row['description']}",
                "",
                "#### Student Profile",
                "```json",
                json.dumps(detail["student_profile"], ensure_ascii=False, indent=2),
                "```",
                "",
                "#### Weak Evaluation",
                f"- expected signal coverage: {_fmt(row['top10_expected_signal_coverage'])}",
                f"- missing signals: {row['missing_expected_signals_json']}",
                f"- zero score count: {row['zero_score_count']}",
                f"- latency: {row['latency_ms']} ms",
                "",
                "#### Top 10 Recommendations",
                "",
                "| rank | mentor_id | name | final_score | company | role | skill | industry | stage | semantic | matched_signals_summary |",
                "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for item in detail["top_recommendations"]:
            display = item["display"]
            breakdown = item["debug"]["score_breakdown"]
            signals = item["debug"]["matched_signals"]
            signal_summary = ", ".join(f"{key}:{len(value)}" for key, value in signals.items() if value) or "-"
            lines.append(
                f"| {display['rank']} | {display['mentor_id']} | {display.get('name') or '-'} | "
                f"{item['debug']['final_score']:.1f} | {breakdown.get('company_match', 0):.1f} | "
                f"{breakdown.get('role_match', 0):.1f} | {breakdown.get('skill_match', 0):.1f} | "
                f"{breakdown.get('industry_match', 0):.1f} | {breakdown.get('stage_match', 0):.1f} | "
                f"{breakdown.get('semantic_match') if breakdown.get('semantic_match') is not None else '-'} | "
                f"{signal_summary} |"
            )
        notes = row.get("notes") or "No automatic issue detected."
        lines.extend(["", "#### Notes for Human Review", f"- {notes}", ""])

    common_missing: dict[str, int] = {}
    for row in summary_rows:
        missing = json.loads(row["missing_expected_signals_json"])
        for values in missing.values():
            for value in values:
                common_missing[value] = common_missing.get(value, 0) + 1
    common_missing_text = ", ".join(
        f"{term}({count})" for term, count in sorted(common_missing.items(), key=lambda item: item[1], reverse=True)[:10]
    )
    lines.extend(
        [
            "## Overall Issues",
            f"- common missing expected signals: {common_missing_text or 'none'}",
            f"- common low-coverage cases: {', '.join(low_coverage) if low_coverage else 'none'}",
            "- recommendation diversity observations: see distinct industry/role columns in summary CSV.",
            "",
            "## Next Actions",
            "- Review missing expected signals before changing aliases.",
            "- Inspect cases where one score component dominates other relevant components.",
            "- Test `--semantic fake` for offline sensitivity; only test `real` explicitly when an embedding service is ready.",
            "- Consider mentor_quality and availability factors after business labels are available.",
        ]
    )
    if show_debug:
        lines.extend(["", "## Debug Output Files", "- See CSV and JSONL files in the same output directory."])
    report = _sanitize_text("\n".join(lines))
    _assert_safe_output(report)
    return report


def _sanitize_text(text: str) -> str:
    value = text
    for term in FORBIDDEN_OUTPUT_TERMS:
        value = value.replace(term, "[关系词已隐藏]")
    return value


def _sanitize_for_output(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_for_output(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_for_output(item) for key, item in value.items()}
    return value


def _assert_safe_output(text: str) -> None:
    if "original_fields" in text:
        raise ValueError("evaluation output must not contain original_fields")
    for term in FORBIDDEN_OUTPUT_TERMS:
        if term in text:
            raise ValueError(f"evaluation output contains forbidden wording: {term}")


__all__ = [
    "EvalCase",
    "GoldLabel",
    "REVIEW_COLUMNS",
    "detail_payload",
    "expected_signal_coverage",
    "load_eval_cases",
    "load_gold_labels",
    "review_rows",
    "run_quality_evaluation",
    "supervised_metrics",
    "weak_case_metrics",
]
