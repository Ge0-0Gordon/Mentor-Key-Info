"""Fast CLI mentor matching over simple extraction JSONL.

This command is intentionally offline: it reads pre-extracted simple mentor
results, parses the student query with an alias table, scores every mentor in
memory, and returns top matches without calling a model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from mentor_agent.matching import (
    AliasIndex,
    RecommendationEngine,
    build_match_result,
    extract_student_profile,
    format_markdown,
    format_rerank_report,
    to_product_dict,
)
from mentor_agent.matching.aliases import DEFAULT_ALIAS_PATH
from mentor_agent.matching.embeddings import default_local_embedding_cache_path
from mentor_agent.matching.reranker import RerankResult, rerank_candidates_with_llm
from mentor_agent.matching.schemas import StudentProfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match a student query to mentor simple results.")
    parser.add_argument("--mentors", required=True, type=Path, help="Path to simple mentor_results.jsonl.")
    parser.add_argument("--query", default=None, help="Student natural-language query.")
    parser.add_argument("--student-profile-json", type=Path, default=None, help="Path to structured StudentProfile JSON.")
    parser.add_argument("--top-k", type=int, default=10, help="Number of mentor cards to return.")
    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=30,
        help="Number of rule-ranked candidates to keep before final top-k.",
    )
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIAS_PATH, help="Alias JSON path.")
    parser.add_argument("--show-score", action="store_true", help="Show final_score in Markdown table.")
    parser.add_argument("--semantic", choices=["none", "fake", "real", "local"], default="none", help="Optional semantic scoring method.")
    parser.add_argument(
        "--embedding-cache",
        type=Path,
        default=None,
        help="Local mentor embedding cache path.",
    )
    parser.add_argument("--embedding-model", default=None, help="Embedding model/cache name.")
    parser.add_argument("--rerank", choices=["none", "llm"], default="none", help="Optional rerank method.")
    parser.add_argument("--rerank-candidate-k", type=int, default=20, help="Number of final-score candidates sent to rerank.")
    parser.add_argument("--rerank-timeout", type=int, default=8, help="LLM rerank timeout in seconds.")
    parser.add_argument("--rerank-report", type=Path, default=None, help="Optional Markdown rerank report path.")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format.",
    )
    return parser.parse_args()


def _load_model_client() -> Any:
    from dotenv import load_dotenv
    from agentrun.integration.langchain import model

    load_dotenv()
    model_service_name = os.getenv("MODEL_SERVICE_NAME")
    model_name = os.getenv("MODEL_NAME")
    if not model_service_name:
        raise ValueError("MODEL_SERVICE_NAME is required for --rerank llm")
    return model(model_service_name, model=model_name)


def _profile_from_json(path: Path) -> StudentProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "student_profile" in payload and isinstance(payload["student_profile"], dict):
        payload = payload["student_profile"]
    payload = dict(payload)
    payload.setdefault("raw_query", _profile_text(payload))
    return StudentProfile.model_validate(payload)


def _profile_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "target_roles",
        "target_companies",
        "target_industries",
        "needed_help",
        "current_stage",
        "preferred_background",
        "keywords",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item)
    return " ".join(parts) or "structured_student_profile"


def _cards_by_rerank(
    rule_candidates: list[Any],
    rerank_result: RerankResult,
    *,
    top_k: int,
) -> list[Any]:
    by_id = {card.mentor_id: card for card in rule_candidates}
    selected = []
    seen = set()
    for mentor_id in rerank_result.reranked_ids:
        card = by_id.get(mentor_id)
        if card is None or mentor_id in seen:
            continue
        selected.append(card)
        seen.add(mentor_id)
        if len(selected) >= top_k:
            break
    for card in rule_candidates:
        if len(selected) >= top_k:
            break
        if card.mentor_id not in seen:
            selected.append(card)
            seen.add(card.mentor_id)
    return selected


def run_match(
    *,
    mentors_path: Path,
    query: str | None = None,
    student_profile: StudentProfile | dict[str, Any] | None = None,
    top_k: int = 10,
    candidate_pool_size: int = 30,
    aliases_path: Path = DEFAULT_ALIAS_PATH,
    rerank: str = "none",
    rerank_candidate_k: int = 20,
    rerank_timeout: int = 8,
    model_client: Any | None = None,
    rerank_report_path: Path | None = None,
    semantic: str = "none",
    embedding_cache_path: Path | None = None,
    embedding_model: str | None = None,
) -> tuple[object, str]:
    aliases = AliasIndex.from_path(aliases_path)
    if student_profile is not None:
        if isinstance(student_profile, StudentProfile):
            profile = student_profile
        else:
            payload = dict(student_profile)
            payload.setdefault("raw_query", _profile_text(payload))
            profile = StudentProfile.model_validate(payload)
    elif query:
        profile = extract_student_profile(query, aliases)
    else:
        raise ValueError("Either query or student_profile is required")

    engine = RecommendationEngine.from_jsonl(
        mentors_path,
        aliases_path,
        semantic_mode=semantic,
        embedding_cache_path=embedding_cache_path or (default_local_embedding_cache_path(embedding_model) if semantic == "local" else None),
        embedding_model=embedding_model,
    )
    artifacts = engine.rank(profile)
    rule_candidates = artifacts.cards
    rerank_result: RerankResult | None = None
    final_candidates = rule_candidates
    if rerank == "llm":
        client = model_client if model_client is not None else _load_model_client()
        rerank_candidates = rule_candidates[:rerank_candidate_k]
        rerank_result = rerank_candidates_with_llm(
            profile,
            rerank_candidates,
            client,
            top_k=top_k,
            timeout_seconds=rerank_timeout,
        )
        reranked_top = _cards_by_rerank(rule_candidates, rerank_result, top_k=top_k)
        selected_ids = {card.mentor_id for card in reranked_top}
        final_candidates = [*reranked_top, *(card for card in rule_candidates if card.mentor_id not in selected_ids)]
    result = build_match_result(
        query=profile.raw_query,
        profile=profile,
        total_mentors=len(engine.documents),
        candidate_cards=final_candidates,
        top_k=top_k,
        used_rerank=rerank == "llm" and bool(rerank_result and rerank_result.success),
        rule_candidate_cards=rule_candidates,
        rerank_result=rerank_result,
        rerank_method=rerank,
        rerank_candidate_k=rerank_candidate_k if rerank == "llm" else 0,
        semantic_method=semantic,
        embedding_model=artifacts.embedding_model,
        embedding_cache_path=artifacts.cache_path,
        embedding_cache_hit_count=artifacts.cache_hit_count,
        embedding_cache_miss_count=artifacts.cache_miss_count,
    )
    if rerank_report_path is not None:
        report = format_rerank_report(
            query=query,
            result=result,
            rule_candidate_cards=rule_candidates,
            final_cards=final_candidates,
            top_k=top_k,
            rerank_candidate_k=rerank_candidate_k,
            forbidden_removed=bool(rerank_result and rerank_result.forbidden_removed),
        )
        rerank_report_path.parent.mkdir(parents=True, exist_ok=True)
        rerank_report_path.write_text(report, encoding="utf-8")
    return result, format_markdown(result)


def main() -> int:
    args = parse_args()
    if not args.query and not args.student_profile_json:
        raise SystemExit("Either --query or --student-profile-json is required")
    profile = _profile_from_json(args.student_profile_json) if args.student_profile_json else None
    result, markdown = run_match(
        mentors_path=args.mentors,
        query=args.query,
        student_profile=profile,
        top_k=args.top_k,
        candidate_pool_size=args.candidate_pool_size,
        aliases_path=args.aliases,
        rerank=args.rerank,
        rerank_candidate_k=args.rerank_candidate_k,
        rerank_timeout=args.rerank_timeout,
        rerank_report_path=args.rerank_report,
        semantic=args.semantic,
        embedding_cache_path=args.embedding_cache,
        embedding_model=args.embedding_model,
    )

    if args.format in {"json", "both"}:
        print(json.dumps(to_product_dict(result), ensure_ascii=False, indent=2))
    if args.format == "both":
        print()
    if args.format in {"markdown", "both"}:
        print(format_markdown(result, show_score=args.show_score))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
