"""Mentor key-information extraction package."""

from .prompts import INDUSTRY_TAXONOMY_VERSION, PROMPT_VERSION
from .schemas import MentorExtraction, MentorInput, MentorResult
from .simple_schemas import (
    SimpleBatchExtractionResponse,
    SimpleMentorBatchResult,
    SimpleMentorExtraction,
    SimpleMentorResult,
)

__all__ = [
    "INDUSTRY_TAXONOMY_VERSION",
    "MentorExtraction",
    "MentorInput",
    "MentorResult",
    "PROMPT_VERSION",
    "SimpleBatchExtractionResponse",
    "SimpleMentorBatchResult",
    "SimpleMentorExtraction",
    "SimpleMentorResult",
]
