"""Build gold label JSONL from manually annotated recommendation review CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FORBIDDEN_OUTPUT_TERMS = ["曾就职", "任职过", "供职", "前员工", "老东家"]
VALID_LABELS = {"good", "acceptable", "bad"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert annotated review CSV into gold labels JSONL.")
    parser.add_argument("--review-csv", required=True, type=Path, help="recommendation_quality_review.csv with human_label.")
    parser.add_argument("--output", required=True, type=Path, help="Output gold labels JSONL path.")
    return parser.parse_args()


def _sanitize_text(value: str) -> str:
    text = str(value or "")
    for term in FORBIDDEN_OUTPUT_TERMS:
        text = text.replace(term, "[关系词已隐藏]")
    return text


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def build_gold_labels_from_review(review_csv: str | Path) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {
            "good_mentor_ids": [],
            "acceptable_mentor_ids": [],
            "bad_mentor_ids": [],
            "notes": [],
        }
    )
    with Path(review_csv).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            case_id = str(row.get("case_id") or "").strip()
            mentor_id = str(row.get("mentor_id") or "").strip()
            label = str(row.get("human_label") or "").strip().lower()
            notes = _sanitize_text(str(row.get("human_notes") or "").strip())
            if not case_id:
                continue
            bucket = grouped[case_id]
            if label in VALID_LABELS and mentor_id:
                bucket[f"{label}_mentor_ids"].append(mentor_id)
            if notes:
                prefix = f"{mentor_id}: " if mentor_id else ""
                bucket["notes"].append(prefix + notes)

    output_rows: list[dict[str, Any]] = []
    for case_id in sorted(grouped):
        bucket = grouped[case_id]
        output_rows.append(
            {
                "case_id": case_id,
                "good_mentor_ids": _dedupe(bucket["good_mentor_ids"]),
                "acceptable_mentor_ids": _dedupe(bucket["acceptable_mentor_ids"]),
                "bad_mentor_ids": _dedupe(bucket["bad_mentor_ids"]),
                "notes": " | ".join(_dedupe(bucket["notes"])),
            }
        )
    return output_rows


def write_gold_labels(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            text = json.dumps(row, ensure_ascii=False)
            if "original_fields" in text:
                raise ValueError("gold label output must not contain original_fields")
            for term in FORBIDDEN_OUTPUT_TERMS:
                if term in text:
                    raise ValueError(f"gold label output contains forbidden wording: {term}")
            handle.write(text + "\n")


def main() -> int:
    args = parse_args()
    rows = build_gold_labels_from_review(args.review_csv)
    write_gold_labels(rows, args.output)
    print(json.dumps({"case_count": len(rows), "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
