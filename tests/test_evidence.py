"""Unit tests for strict and deliberately narrow loose evidence matching."""

from mentor_agent.evidence import classify_evidence_match, validate_evidence
from mentor_agent.schemas import Evidence, EvidenceMatchType, OriginalFields


def _original_fields() -> OriginalFields:
    return OriginalFields.model_validate(
        {
            "序号": 1,
            "导师姓名": "测试导师",
            "性别": "女",
            "城市": "杭州",
            "职业年限": 12,
            "可辅导学员职级": "P5-P7",
            "行业标签": "软件与信息技术",
            "从业经历": "曾任星河科技人才发展经理。",
            "背景经验": "擅长简历优化，面试辅导。",
        }
    )


def test_strict_evidence_match() -> None:
    evidence = Evidence(source_field="从业经历", quote="星河科技人才发展经理")

    checked = validate_evidence(evidence, _original_fields())

    assert checked.match_type is EvidenceMatchType.STRICT


def test_loose_evidence_match_uses_nfkc_case_whitespace_and_limited_punctuation() -> None:
    evidence = Evidence(
        source_field="背景经验",
        quote="擅长 简历优化; 面试辅导",
    )

    checked = validate_evidence(evidence, _original_fields())

    assert checked.match_type is EvidenceMatchType.LOOSE


def test_evidence_does_not_cross_source_fields() -> None:
    evidence = Evidence(source_field="城市", quote="星河科技")

    match_type = classify_evidence_match(evidence, _original_fields())

    assert match_type is EvidenceMatchType.INVALID
