"""Optional rerank helpers and guardrails.

The MVP keeps customer-facing matching offline by default. These helpers make a
future LLM rerank step testable without allowing it to invent employment claims.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .schemas import LlmRerankResponse, MentorCandidateCard, RerankResponse, StudentProfile


UNSAFE_EMPLOYER_PHRASES = ("曾就职", "任职于", "供职于", "前员工", "老东家", "曾任职")


class RerankValidationError(ValueError):
    """Raised when rerank output is not safe to use."""


def build_rerank_prompt(query: str, candidates: list[MentorCandidateCard]) -> str:
    """Build a compact future LLM rerank prompt.

    The prompt is not used by the default CLI path; it documents and tests the
    safe contract for a future online reranker.
    """

    cards = [
        {
            "mentor_id": card.mentor_id,
            "name": card.name,
            "city": card.city,
            "industries": card.industries,
            "companies": card.companies,
            "roles": card.roles,
            "skills": card.skills,
            "target_mentees": card.target_mentees,
            "highlights": card.highlights[:5],
            "summary": card.summary,
            "matched_signals": card.matched_signals.model_dump(),
            "rule_score": card.rule_score,
        }
        for card in candidates
    ]
    payload = {"query": query, "candidate_cards": cards}
    return (
        "你是导师推荐重排器。只基于 candidate_cards 推荐，不要编造。\n"
        "推荐理由必须来自 matched_signals 或 candidate card。\n"
        "companies 只能表述为“资料中出现相关公司/机构”，不能说“曾就职”。\n"
        "只输出 JSON：{\"recommendations\":[{\"mentor_id\":\"...\",\"rank\":1,"
        "\"fit_score\":90,\"fit_reasons\":[],\"possible_gap\":null}]}\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )


def validate_rerank_response(raw: object, candidates: list[MentorCandidateCard]) -> RerankResponse:
    try:
        response = RerankResponse.model_validate(raw)
    except ValidationError as exc:
        raise RerankValidationError(f"invalid rerank response: {exc}") from exc

    candidate_ids = {card.mentor_id for card in candidates}
    ranks = set()
    for item in response.recommendations:
        if item.mentor_id not in candidate_ids:
            raise RerankValidationError(f"rerank returned unknown mentor_id: {item.mentor_id}")
        if item.rank in ranks:
            raise RerankValidationError(f"duplicate rerank rank: {item.rank}")
        ranks.add(item.rank)
        texts = [*item.fit_reasons, item.possible_gap or ""]
        if any(phrase in text for text in texts for phrase in UNSAFE_EMPLOYER_PHRASES):
            raise RerankValidationError("rerank reason contains unverified employer wording")

    return response


@dataclass(frozen=True)
class RerankedItem:
    mentor_id: str
    rank: int
    llm_fit_score: float | None = None
    rerank_note: str | None = None


@dataclass(frozen=True)
class RerankResult:
    success: bool
    fallback_used: bool
    latency_ms: int
    reranked_ids: list[str]
    error_message: str | None = None
    items: list[RerankedItem] = field(default_factory=list)
    forbidden_removed: bool = False


def _invoke_model(model_client: Any, messages: list[dict[str, str]]) -> Any:
    invoke = getattr(model_client, "invoke", None)
    if callable(invoke):
        return invoke(messages)
    if callable(model_client):
        return model_client(messages)
    raise TypeError("model_client must be callable or expose invoke(messages)")


def _response_content(response: Any) -> Any:
    content = getattr(response, "content", None)
    if content is not None:
        return content
    if isinstance(response, Mapping) and set(response) == {"content"}:
        return response["content"]
    return response


def _sanitize_error(exc: BaseException) -> str:
    text = str(exc).replace("\n", " ").strip()
    for marker in ("AccessKey", "API Key", "Authorization", ".env", "token"):
        text = text.replace(marker, "[redacted]")
    return text[:200] or exc.__class__.__name__


def _clean_note(note: str | None) -> tuple[str | None, bool]:
    if not note:
        return None, False
    cleaned = note.strip()[:120]
    removed = False
    for phrase in UNSAFE_EMPLOYER_PHRASES:
        if phrase in cleaned:
            cleaned = cleaned.replace(phrase, "")
            removed = True
    cleaned = " ".join(cleaned.split())
    return cleaned or None, removed


def _signal_values(signals: list[Any]) -> list[str]:
    values = []
    for signal in signals[:3]:
        value = getattr(signal, "canonical", None) or getattr(signal, "matched_term", None)
        if value and value not in values:
            values.append(value)
    return values


def _compact_values(values: list[str], *, limit: int = 3, max_chars: int = 18) -> list[str]:
    compact: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in compact:
            continue
        compact.append(text[:max_chars])
        if len(compact) >= limit:
            break
    return compact


def _compact_student_profile(profile: StudentProfile) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": profile.raw_query[:180]}
    for field in (
        "target_industries",
        "target_companies",
        "target_roles",
        "current_stage",
        "needed_help",
        "preferred_background",
        "keywords",
    ):
        values = _compact_values(getattr(profile, field), limit=5, max_chars=20)
        if values:
            payload[field] = values
    constraints = profile.constraints.model_dump(mode="json")
    compact_constraints = {key: value for key, value in constraints.items() if value}
    if compact_constraints:
        payload["constraints"] = compact_constraints
    return payload


def _card_text(card: MentorCandidateCard) -> str:
    parts: list[str] = []
    field_values = [
        ("city", [card.city] if card.city else []),
        ("industries", card.industries),
        ("companies", card.companies),
        ("roles", card.roles),
        ("skills", card.skills),
        ("mentees", card.target_mentees),
    ]
    for label, values in field_values:
        compact = _compact_values(values)
        if compact:
            parts.append(f"{label}:{'/'.join(compact)}")
    highlights = _compact_values(card.highlights, limit=2, max_chars=24)
    if highlights:
        parts.append(f"highlights:{'/'.join(highlights)}")
    if card.summary:
        parts.append(f"summary:{card.summary.strip()[:60]}")
    return "; ".join(parts)[:260]


def _compact_matched_signals(card: MentorCandidateCard) -> list[str]:
    values: list[str] = []
    for signals in (
        card.matched_signals.companies,
        card.matched_signals.roles,
        card.matched_signals.skills,
        card.matched_signals.target_mentees,
        card.matched_signals.industries,
        card.matched_signals.keywords,
    ):
        for value in _signal_values(signals):
            if value not in values:
                values.append(value)
            if len(values) >= 8:
                return values
    return values


def _candidate_payload(cards: list[MentorCandidateCard]) -> list[dict[str, Any]]:
    payload = []
    for idx, card in enumerate(cards, start=1):
        payload.append(
            {
                "mentor_id": card.mentor_id,
                "rule_rank": idx,
                "rule_score": card.final_score,
                "name": card.name,
                "card": _card_text(card),
                "matched": _compact_matched_signals(card),
            }
        )
    return payload


def build_rerank_messages(
    student_profile: StudentProfile,
    candidate_cards: list[MentorCandidateCard],
    *,
    top_k: int = 10,
) -> list[dict[str, str]]:
    payload = {
        "student": _compact_student_profile(student_profile),
        "top_k": top_k,
        "candidates": _candidate_payload(candidate_cards),
    }
    system = (
        "You are a fast mentor reranker. Rank only the given candidates. "
        "Use only candidate data; do not invent facts. "
        "Companies are signals only, not verified employment. "
        "Return compact JSON only, no Markdown, no explanation."
    )
    user = (
        'Return exactly: {"ordered_mentor_ids":["service_mentor:1"],"scores":[90]}. '
        "ordered_mentor_ids must contain top_k unique IDs from candidates, best first. "
        "scores is optional and must be short. "
        "\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_llm_rerank_payload(response: Any) -> Mapping[str, Any]:
    content = _response_content(response)
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, Mapping):
        return dict(content)
    raise TypeError("rerank model response must be JSON text, a mapping, or expose content")


def _validate_llm_rerank_response(
    payload: Mapping[str, Any],
    candidate_cards: list[MentorCandidateCard],
    *,
    top_k: int,
) -> tuple[list[RerankedItem], bool]:
    try:
        parsed = LlmRerankResponse.model_validate(payload)
    except ValidationError as exc:
        raise RerankValidationError(f"invalid rerank response: {exc.error_count()} validation error(s)") from exc
    if parsed.ordered_mentor_ids:
        candidate_ids = {card.mentor_id for card in candidate_cards}
        seen_ids: set[str] = set()
        items: list[RerankedItem] = []
        for rank, mentor_id in enumerate(parsed.ordered_mentor_ids, start=1):
            if mentor_id not in candidate_ids:
                raise RerankValidationError(f"rerank returned unknown mentor_id: {mentor_id}")
            if mentor_id in seen_ids:
                raise RerankValidationError(f"rerank returned duplicate mentor_id: {mentor_id}")
            seen_ids.add(mentor_id)
            score = parsed.scores[rank - 1] if rank <= len(parsed.scores) else None
            items.append(RerankedItem(mentor_id=mentor_id, rank=rank, llm_fit_score=score))
        if len(items) < min(top_k, len(candidate_cards)):
            raise RerankValidationError("rerank response returned too few results")
        return items, False

    if not parsed.reranked_results:
        raise RerankValidationError("rerank response returned no results")
    if len(parsed.reranked_results) < min(top_k, len(candidate_cards)):
        raise RerankValidationError("rerank response returned too few results")

    candidate_ids = {card.mentor_id for card in candidate_cards}
    seen_ids: set[str] = set()
    seen_ranks: set[int] = set()
    items: list[RerankedItem] = []
    forbidden_removed = False
    for item in sorted(parsed.reranked_results, key=lambda value: value.rank):
        if item.mentor_id not in candidate_ids:
            raise RerankValidationError(f"rerank returned unknown mentor_id: {item.mentor_id}")
        if item.mentor_id in seen_ids:
            raise RerankValidationError(f"rerank returned duplicate mentor_id: {item.mentor_id}")
        if item.rank in seen_ranks:
            raise RerankValidationError(f"rerank returned duplicate rank: {item.rank}")
        seen_ids.add(item.mentor_id)
        seen_ranks.add(item.rank)
        note, removed = _clean_note(item.rerank_note)
        forbidden_removed = forbidden_removed or removed
        items.append(
            RerankedItem(
                mentor_id=item.mentor_id,
                rank=item.rank,
                llm_fit_score=item.llm_fit_score,
                rerank_note=note,
            )
        )
    return items, forbidden_removed


def rerank_candidates_with_llm(
    student_profile: StudentProfile,
    candidate_cards: list[MentorCandidateCard],
    model_client: Any,
    *,
    top_k: int = 10,
    timeout_seconds: int = 8,
) -> RerankResult:
    started = perf_counter()
    fallback_ids = [card.mentor_id for card in candidate_cards[:top_k]]
    try:
        messages = build_rerank_messages(student_profile, candidate_cards, top_k=top_k)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_invoke_model, model_client, messages)
        try:
            response = future.result(timeout=timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        payload = _parse_llm_rerank_payload(response)
        items, forbidden_removed = _validate_llm_rerank_response(
            payload,
            candidate_cards,
            top_k=top_k,
        )
        return RerankResult(
            success=True,
            fallback_used=False,
            latency_ms=int((perf_counter() - started) * 1000),
            reranked_ids=[item.mentor_id for item in items],
            items=items,
            forbidden_removed=forbidden_removed,
        )
    except TimeoutError:
        error_message = f"rerank timeout after {timeout_seconds}s"
    except Exception as exc:
        error_message = _sanitize_error(exc)

    return RerankResult(
        success=False,
        fallback_used=True,
        latency_ms=int((perf_counter() - started) * 1000),
        reranked_ids=fallback_ids,
        error_message=error_message,
    )


__all__ = [
    "RerankValidationError",
    "RerankResult",
    "RerankedItem",
    "UNSAFE_EMPLOYER_PHRASES",
    "build_rerank_messages",
    "build_rerank_prompt",
    "rerank_candidates_with_llm",
    "validate_rerank_response",
]
