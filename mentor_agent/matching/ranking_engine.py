"""Low-latency in-memory recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .aliases import AliasIndex
from .embeddings import (
    DEFAULT_LOCAL_EMBEDDING_MODEL,
    EmbeddingCache,
    FAKE_EMBEDDING_MODEL,
    default_local_embedding_cache_path,
    get_embedding,
)
from .formatter import build_match_result
from .mentor_index import MentorDocument, load_mentor_documents
from .schemas import MatchResult, StudentProfile
from .scorer import SemanticContext, build_student_search_text, rank_candidates


@dataclass
class RankingArtifacts:
    cards: list
    embedding_model: str | None
    cache_path: str | None
    cache_hit_count: int
    cache_miss_count: int


class RecommendationEngine:
    def __init__(
        self,
        *,
        documents: list[MentorDocument],
        aliases: AliasIndex,
        semantic_mode: str = "none",
        embedding_cache_path: str | Path | None = None,
        embedding_model: str | None = None,
    ):
        self.documents = documents
        self.aliases = aliases
        self.semantic_mode = semantic_mode
        self.embedding_model = embedding_model or (
            FAKE_EMBEDDING_MODEL
            if semantic_mode == "fake"
            else DEFAULT_LOCAL_EMBEDDING_MODEL
            if semantic_mode == "local"
            else None
        )
        if embedding_cache_path:
            self.embedding_cache_path = Path(embedding_cache_path)
        elif semantic_mode == "local":
            self.embedding_cache_path = default_local_embedding_cache_path(self.embedding_model)
        else:
            self.embedding_cache_path = None

    @classmethod
    def from_jsonl(
        cls,
        mentors_path: str | Path,
        aliases_path: str | Path,
        *,
        semantic_mode: str = "none",
        embedding_cache_path: str | Path | None = None,
        embedding_model: str | None = None,
    ) -> "RecommendationEngine":
        return cls(
            documents=load_mentor_documents(mentors_path),
            aliases=AliasIndex.from_path(aliases_path),
            semantic_mode=semantic_mode,
            embedding_cache_path=embedding_cache_path,
            embedding_model=embedding_model,
        )

    def rank(self, profile: StudentProfile) -> RankingArtifacts:
        semantic_context: SemanticContext | None = None
        cache: EmbeddingCache | None = None
        resolved_embedding_model = self.embedding_model
        if self.semantic_mode != "none":
            resolved_embedding_model = resolved_embedding_model or self.semantic_mode
            cache = EmbeddingCache(self.embedding_cache_path)
            query_embedding = get_embedding(
                build_student_search_text(profile),
                method=self.semantic_mode,
                embedding_model=resolved_embedding_model,
            )
            semantic_context = SemanticContext(
                method=self.semantic_mode,
                embedding_model=resolved_embedding_model,
                cache=cache,
                query_embedding=query_embedding,
            )
        cards = rank_candidates(
            self.documents,
            profile,
            self.aliases,
            candidate_pool_size=len(self.documents),
            semantic_context=semantic_context,
        )
        if cache:
            cache.save()
        return RankingArtifacts(
            cards=cards,
            embedding_model=resolved_embedding_model,
            cache_path=str(self.embedding_cache_path) if self.semantic_mode != "none" and self.embedding_cache_path else None,
            cache_hit_count=cache.stats.hit_count if cache else 0,
            cache_miss_count=cache.stats.miss_count if cache else 0,
        )

    def recommend(self, profile: StudentProfile, *, top_k: int = 10) -> MatchResult:
        artifacts = self.rank(profile)
        return build_match_result(
            query=profile.raw_query,
            profile=profile,
            total_mentors=len(self.documents),
            candidate_cards=artifacts.cards,
            top_k=top_k,
            rule_candidate_cards=artifacts.cards,
            semantic_method=self.semantic_mode,
            embedding_model=artifacts.embedding_model,
            embedding_cache_path=artifacts.cache_path,
            embedding_cache_hit_count=artifacts.cache_hit_count,
            embedding_cache_miss_count=artifacts.cache_miss_count,
        )


__all__ = ["RecommendationEngine", "RankingArtifacts"]
