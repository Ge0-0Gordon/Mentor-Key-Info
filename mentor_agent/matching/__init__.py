"""Fast offline mentor matching."""

from .aliases import AliasIndex
from .formatter import build_match_result, format_markdown, format_rerank_report, to_product_dict
from .mentor_index import load_mentor_documents
from .scorer import rank_candidates, score_mentor
from .student_profile import extract_student_profile

__all__ = [
    "AliasIndex",
    "build_match_result",
    "extract_student_profile",
    "format_markdown",
    "format_rerank_report",
    "load_mentor_documents",
    "rank_candidates",
    "score_mentor",
    "to_product_dict",
]
