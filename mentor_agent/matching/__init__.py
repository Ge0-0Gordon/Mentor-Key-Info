"""Fast offline mentor matching."""

from .aliases import AliasIndex
from .embeddings import EmbeddingCache, cosine_similarity, fake_hash_embedding
from .formatter import build_match_result, format_markdown, format_rerank_report, to_product_dict
from .mentor_index import load_mentor_documents
from .ranking_engine import RecommendationEngine
from .scorer import SemanticContext, build_student_search_text, rank_candidates, score_mentor
from .student_profile import extract_student_profile

__all__ = [
    "AliasIndex",
    "EmbeddingCache",
    "RecommendationEngine",
    "SemanticContext",
    "build_match_result",
    "build_student_search_text",
    "cosine_similarity",
    "extract_student_profile",
    "fake_hash_embedding",
    "format_markdown",
    "format_rerank_report",
    "load_mentor_documents",
    "rank_candidates",
    "score_mentor",
    "to_product_dict",
]
