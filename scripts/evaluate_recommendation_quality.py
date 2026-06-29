"""Run offline recommendation quality evaluation.

The script calls the existing recommendation-v1 engine over structured
StudentProfile cases. It does not call LLMs, databases, frontends, or real
embedding services unless the user explicitly passes a supported semantic mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_agent.matching.aliases import DEFAULT_ALIAS_PATH
from mentor_agent.matching.embeddings import default_local_embedding_cache_path
from mentor_agent.matching.evaluation import run_quality_evaluation


def parse_args() -> argparse.Namespace:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="Evaluate recommendation-v1 quality offline.")
    parser.add_argument("--mentors", required=True, type=Path, help="Path to simple mentor_results.jsonl.")
    parser.add_argument("--cases", type=Path, default=Path("eval/student_profiles_eval.jsonl"), help="Eval cases JSONL.")
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIAS_PATH, help="Matching aliases JSON.")
    parser.add_argument("--top-k", type=int, default=10, help="Top K mentor cards to evaluate.")
    parser.add_argument(
        "--semantic",
        choices=["none", "fake", "real", "local", "local-scoped-bonus"],
        default="none",
        help="Semantic mode. local uses sentence-transformers; real requires a configured embedding provider.",
    )
    parser.add_argument("--embedding-model", default=None, help="Embedding model name for semantic real or cache identity.")
    parser.add_argument(
        "--embedding-cache",
        type=Path,
        default=None,
        help="Mentor embedding cache path. Defaults to output-dir cache for semantic modes.",
    )
    parser.add_argument("--gold-labels", type=Path, default=None, help="Optional human gold labels JSONL.")
    parser.add_argument("--show-debug", action="store_true", help="Add debug file note to Markdown report.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / f"recommendation_eval_{timestamp}",
        help="Output directory for report, CSV, and JSONL files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    embedding_cache = args.embedding_cache
    if args.semantic in {"local", "local-scoped-bonus"} and embedding_cache is None:
        embedding_cache = default_local_embedding_cache_path(args.embedding_model)
    try:
        summary = run_quality_evaluation(
            mentors_path=args.mentors,
            cases_path=args.cases,
            aliases_path=args.aliases,
            output_dir=args.output_dir,
            top_k=args.top_k,
            semantic=args.semantic,
            embedding_model=args.embedding_model,
            embedding_cache_path=embedding_cache,
            gold_labels_path=args.gold_labels,
            show_debug=args.show_debug,
        )
    except RuntimeError as exc:
        if args.semantic == "real" and "real embedding provider not available" in str(exc):
            print("real embedding provider not available", file=sys.stderr)
            return 2
        if args.semantic in {"local", "local-scoped-bonus"} and "semantic local" in str(exc):
            print(str(exc), file=sys.stderr)
            return 2
        raise
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
