"""Fast CLI mentor matching over simple extraction JSONL.

This command is intentionally offline: it reads pre-extracted simple mentor
results, parses the student query with an alias table, scores every mentor in
memory, and returns top matches without calling a model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mentor_agent.matching import (
    AliasIndex,
    build_match_result,
    extract_student_profile,
    format_markdown,
    load_mentor_documents,
    rank_candidates,
)
from mentor_agent.matching.aliases import DEFAULT_ALIAS_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match a student query to mentor simple results.")
    parser.add_argument("--mentors", required=True, type=Path, help="Path to simple mentor_results.jsonl.")
    parser.add_argument("--query", required=True, help="Student natural-language query.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of recommendations to return.")
    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=30,
        help="Number of rule-ranked candidates to keep before final top-k.",
    )
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIAS_PATH, help="Alias JSON path.")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format.",
    )
    return parser.parse_args()


def run_match(
    *,
    mentors_path: Path,
    query: str,
    top_k: int = 5,
    candidate_pool_size: int = 30,
    aliases_path: Path = DEFAULT_ALIAS_PATH,
) -> tuple[object, str]:
    aliases = AliasIndex.from_path(aliases_path)
    documents = load_mentor_documents(mentors_path)
    profile = extract_student_profile(query, aliases)
    candidates = rank_candidates(
        documents,
        profile,
        aliases,
        candidate_pool_size=max(top_k, candidate_pool_size),
    )
    result = build_match_result(
        query=query,
        profile=profile,
        total_mentors=len(documents),
        candidate_cards=candidates,
        top_k=top_k,
    )
    return result, format_markdown(result)


def main() -> int:
    args = parse_args()
    result, markdown = run_match(
        mentors_path=args.mentors,
        query=args.query,
        top_k=args.top_k,
        candidate_pool_size=args.candidate_pool_size,
        aliases_path=args.aliases,
    )

    if args.format in {"json", "both"}:
        print(result.model_dump_json(by_alias=True, ensure_ascii=False, indent=2))
    if args.format == "both":
        print()
    if args.format in {"markdown", "both"}:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
