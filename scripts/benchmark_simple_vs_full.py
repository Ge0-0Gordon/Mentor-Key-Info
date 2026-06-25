"""Compare simple and full extraction payload/result sizes without printing source text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mentor_agent.excel_io import load_mentor_inputs_with_report
from mentor_agent.extractor import build_extraction_messages
from mentor_agent.simple_prompts import build_simple_extraction_messages


def _message_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(message.get("content", "")) for message in messages)


def _read_result_metrics(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"count": 0}

    lengths: list[int] = []
    latencies: list[int] = []
    attempts: list[int] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            lengths.append(len(line.rstrip("\n")))
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            processing = payload.get("processing") or {}
            latency = processing.get("latency_ms")
            attempt_count = processing.get("attempt_count")
            if isinstance(latency, int):
                latencies.append(latency)
            if isinstance(attempt_count, int):
                attempts.append(attempt_count)

    return {
        "count": len(lengths),
        "avg_response_json_chars": round(mean(lengths), 1) if lengths else None,
        "avg_latency_ms": round(mean(latencies), 1) if latencies else None,
        "avg_attempt_count": round(mean(attempts), 2) if attempts else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare simple vs full mentor extraction payload sizes."
    )
    parser.add_argument("--input", "-i", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--simple-results-jsonl", type=Path)
    parser.add_argument("--full-results-jsonl", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = load_mentor_inputs_with_report(args.input)
    selected = report.inputs[args.offset :]
    if args.limit is not None:
        selected = selected[: args.limit]

    simple_lengths = [
        _message_chars(build_simple_extraction_messages(mentor_input))
        for mentor_input in selected
    ]
    full_lengths = [
        _message_chars(build_extraction_messages(mentor_input))
        for mentor_input in selected
    ]

    summary = {
        "source_file": report.summary.source_file,
        "selected_count": len(selected),
        "simple_request_avg_chars": round(mean(simple_lengths), 1)
        if simple_lengths
        else 0,
        "full_request_avg_chars": round(mean(full_lengths), 1)
        if full_lengths
        else 0,
        "simple_results": _read_result_metrics(args.simple_results_jsonl),
        "full_results": _read_result_metrics(args.full_results_jsonl),
    }
    if summary["full_request_avg_chars"]:
        summary["request_char_reduction_pct"] = round(
            100
            * (
                1
                - summary["simple_request_avg_chars"]
                / summary["full_request_avg_chars"]
            ),
            1,
        )

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
