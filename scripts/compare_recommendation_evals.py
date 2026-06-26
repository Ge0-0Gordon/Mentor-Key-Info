"""Compare two recommendation quality evaluation output directories."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two recommendation quality evaluation outputs.")
    parser.add_argument("--none-dir", required=True, type=Path)
    parser.add_argument("--real-dir", required=True, type=Path, help="Right-side eval dir, e.g. semantic real or local.")
    parser.add_argument("--right-label", default="semantic real", help="Right-side label shown in the report.")
    parser.add_argument("--gold-labels", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _read_summary(directory: Path) -> list[dict[str, str]]:
    with (directory / "recommendation_quality_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_details(directory: Path) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    with (directory / "recommendation_quality_details.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                details[row["case_id"]] = row
    return details


def _read_gold(path: Path) -> dict[str, dict[str, set[str]]]:
    labels: dict[str, dict[str, set[str]]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            labels[row["case_id"]] = {
                "good": set(row.get("good_mentor_ids", [])),
                "acceptable": set(row.get("acceptable_mentor_ids", [])),
                "bad": set(row.get("bad_mentor_ids", [])),
            }
    return labels


def _float(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        return 0.0
    return float(value)


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95 + 0.9999) - 1))
    return round(ordered[index], 4)


def _top10_changed_total(left_details: dict[str, dict[str, Any]], right_details: dict[str, dict[str, Any]]) -> float:
    total = 0
    for case_id, right_detail in right_details.items():
        left_ids = set(_ids(left_details.get(case_id, {})))
        right_ids = set(_ids(right_detail))
        total += len(left_ids.symmetric_difference(right_ids))
    return float(total)


def _aggregate(
    rows: list[dict[str, str]],
    details: dict[str, dict[str, Any]],
    *,
    left_details_for_change: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float]:
    supervised = [detail.get("supervised_metrics") or {} for detail in details.values()]
    supervised = [row for row in supervised if row]
    all_items = [item for detail in details.values() for item in detail.get("top_recommendations", [])]
    semantic_values = [
        item["debug"]["score_breakdown"].get("semantic_match")
        for item in all_items
        if item["debug"]["score_breakdown"].get("semantic_match") is not None
    ]
    return {
        "avg latency": _mean([_float(row, "latency_ms") for row in rows]),
        "p95 latency": _p95([_float(row, "latency_ms") for row in rows]),
        "Hit@1": _mean([_float(row, "Hit@1") for row in supervised]),
        "Hit@3": _mean([_float(row, "Hit@3") for row in supervised]),
        "Hit@5": _mean([_float(row, "Hit@5") for row in supervised]),
        "Hit@10": _mean([_float(row, "Hit@10") for row in supervised]),
        "MRR": _mean([_float(row, "MRR") for row in supervised]),
        "NDCG@10": _mean([_float(row, "NDCG@10") for row in supervised]),
        "bad_in_top10_count": sum(_float(row, "bad_in_top10_count") for row in supervised),
        "unknown_in_top10_count": sum(_float(row, "unknown_in_top10_count") for row in rows),
        "avg final_score": _mean([item["debug"]["final_score"] for item in all_items]),
        "avg semantic_match": _mean([float(value) for value in semantic_values]),
        "Top10 changed count": _top10_changed_total(left_details_for_change, details) if left_details_for_change is not None else 0.0,
    }


def _ids(detail: dict[str, Any]) -> list[str]:
    return [item["display"]["mentor_id"] for item in detail.get("top_recommendations", [])]


def _best_rank(ids: list[str], wanted: set[str]) -> int | None:
    for index, mentor_id in enumerate(ids, start=1):
        if mentor_id in wanted:
            return index
    return None


def _rank_delta(none_ids: list[str], real_ids: list[str], wanted: set[str]) -> str:
    before = _best_rank(none_ids, wanted)
    after = _best_rank(real_ids, wanted)
    if before is None and after is None:
        return ""
    if before is None:
        return f"new@{after}"
    if after is None:
        return "dropped"
    return str(before - after)


def render_compare_report(none_dir: Path, real_dir: Path, gold_labels: Path, *, right_label: str = "semantic real") -> str:
    none_rows = _read_summary(none_dir)
    real_rows = _read_summary(real_dir)
    none_details = _read_details(none_dir)
    real_details = _read_details(real_dir)
    labels = _read_gold(gold_labels)
    none_metrics = _aggregate(none_rows, none_details)
    real_metrics = _aggregate(real_rows, real_details, left_details_for_change=none_details)
    metric_order = [
        "avg latency",
        "p95 latency",
        "Hit@1",
        "Hit@3",
        "Hit@5",
        "Hit@10",
        "MRR",
        "NDCG@10",
        "bad_in_top10_count",
        "unknown_in_top10_count",
        "avg final_score",
        "avg semantic_match",
        "Top10 changed count",
    ]
    lines = [
        f"# Recommendation Eval Compare: semantic none vs {right_label.replace('semantic ', '')}",
        "",
        f"| metric | semantic none | {right_label} | delta |",
        "| ------ | ------------: | ------------: | ----: |",
    ]
    for metric in metric_order:
        none_value = none_metrics.get(metric, 0.0)
        real_value = real_metrics.get(metric, 0.0)
        lines.append(f"| {metric} | {none_value:.4f} | {real_value:.4f} | {real_value - none_value:.4f} |")

    lines.extend(
        [
            "",
            "## Per Case Changes",
            "",
            "| case_id | description | none Top10 mentor_ids | real Top10 mentor_ids | Top10 changed count | good rank change | bad rank change | unknown newly introduced mentors | needs review |",
            "|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    for case_id in sorted(real_details):
        none_detail = none_details.get(case_id, {})
        real_detail = real_details[case_id]
        none_ids = _ids(none_detail)
        real_ids = _ids(real_detail)
        label = labels.get(case_id, {"good": set(), "acceptable": set(), "bad": set()})
        labeled = label["good"] | label["acceptable"] | label["bad"]
        introduced = [mentor_id for mentor_id in real_ids if mentor_id not in none_ids]
        unknown_new = [mentor_id for mentor_id in introduced if mentor_id not in labeled]
        changed_count = len(set(none_ids).symmetric_difference(set(real_ids)))
        needs_review = bool(unknown_new)
        description = str(real_detail.get("description") or "").replace("|", "/")
        lines.append(
            f"| {case_id} | {description} | {', '.join(none_ids)} | {', '.join(real_ids)} | "
            f"{changed_count} | {_rank_delta(none_ids, real_ids, label['good'] | label['acceptable'])} | "
            f"{_rank_delta(none_ids, real_ids, label['bad'])} | {', '.join(unknown_new) or '-'} | "
            f"{'yes' if needs_review else 'no'} |"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = render_compare_report(args.none_dir, args.real_dir, args.gold_labels, right_label=args.right_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
