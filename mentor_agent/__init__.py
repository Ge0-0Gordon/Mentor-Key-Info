"""Mentor key-information extraction package."""

from .prompts import INDUSTRY_TAXONOMY_VERSION, PROMPT_VERSION
from .schemas import MentorExtraction, MentorInput, MentorResult

__all__ = [
    "INDUSTRY_TAXONOMY_VERSION",
    "MentorExtraction",
    "MentorInput",
    "MentorResult",
    "PROMPT_VERSION",
]
