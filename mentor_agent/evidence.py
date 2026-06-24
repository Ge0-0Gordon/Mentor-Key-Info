"""Deterministic evidence matching for mentor extraction results."""

from __future__ import annotations

import unicodedata

from .schemas import Evidence, EvidenceMatchType, OriginalFields


_LOOSE_PUNCTUATION = "，。；：、,.!?！？;:()（）[]【】{}《》<>“”‘’\"'`·-_—/\\|"
_PUNCTUATION_TABLE = str.maketrans("", "", _LOOSE_PUNCTUATION)


def normalize_loose_text(value: str) -> str:
    """Apply the deliberately narrow V1 loose-match normalization."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_whitespace = "".join(char for char in normalized if not char.isspace())
    return without_whitespace.translate(_PUNCTUATION_TABLE)


def classify_evidence_match(
    evidence: Evidence,
    original_fields: OriginalFields,
) -> EvidenceMatchType:
    """Classify an evidence quote against its declared source field only."""

    source_values = original_fields.model_dump(by_alias=True)
    source_value = source_values.get(evidence.source_field.value)
    if source_value is None:
        return EvidenceMatchType.INVALID

    source_text = str(source_value)
    if evidence.quote in source_text:
        return EvidenceMatchType.STRICT

    normalized_quote = normalize_loose_text(evidence.quote)
    normalized_source = normalize_loose_text(source_text)
    if normalized_quote and normalized_quote in normalized_source:
        return EvidenceMatchType.LOOSE
    return EvidenceMatchType.INVALID


def validate_evidence(
    evidence: Evidence,
    original_fields: OriginalFields,
) -> Evidence:
    """Return an Evidence copy with program-computed match_type."""

    return evidence.model_copy(
        update={"match_type": classify_evidence_match(evidence, original_fields)}
    )


__all__ = [
    "classify_evidence_match",
    "normalize_loose_text",
    "validate_evidence",
]
