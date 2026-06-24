"""Unit tests for Stage 3 deterministic normalization helpers."""

from mentor_agent.normalizers import (
    deduplicate_items,
    normalize_company_name,
    normalize_industry,
    normalize_skill,
)
from mentor_agent.schemas import MappingStatus


def test_safe_company_alias_is_mapped_without_legal_name_completion() -> None:
    result = normalize_company_name("字节")

    assert result.normalized_value == "字节跳动"
    assert result.mapping_status is MappingStatus.MAPPED


def test_unknown_company_keeps_raw_and_is_unmapped() -> None:
    result = normalize_company_name("星河深海实验室")

    assert result.normalized_value == "星河深海实验室"
    assert result.mapping_status is MappingStatus.UNMAPPED


def test_ambiguous_company_has_no_normalized_value() -> None:
    result = normalize_company_name("中信")

    assert result.normalized_value is None
    assert result.mapping_status is MappingStatus.AMBIGUOUS


def test_outside_taxonomy_industry_keeps_raw_and_is_unmapped() -> None:
    result = normalize_industry("深海机器人服务")

    assert result.normalized_value == "深海机器人服务"
    assert result.mapping_status is MappingStatus.UNMAPPED


def test_taxonomy_industry_and_safe_alias_can_be_mapped() -> None:
    assert normalize_industry("软件与信息技术").mapping_status is MappingStatus.MAPPED
    assert normalize_industry("AI").normalized_value == "人工智能、大数据与云计算"


def test_free_form_skill_is_preserved_when_no_safe_mapping_exists() -> None:
    result = normalize_skill("跨星际团队职业叙事设计")

    assert result.normalized_value == "跨星际团队职业叙事设计"
    assert result.mapping_status is MappingStatus.UNMAPPED


def test_deduplicate_items_keeps_first_occurrence() -> None:
    items = [
        {"raw": "简历修改", "source": 1},
        {"raw": "简历修改", "source": 2},
        {"raw": "面试辅导", "source": 3},
    ]

    result = deduplicate_items(items, key=lambda item: item["raw"])

    assert result == [items[0], items[2]]
