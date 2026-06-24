"""Small, deterministic V1 alias maps and deduplication helpers."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

from pydantic import BaseModel

from .prompts import SOFT_INDUSTRY_TAXONOMY
from .schemas import MappingStatus


@dataclass(frozen=True)
class NormalizationResult:
    normalized_value: str | None
    mapping_status: MappingStatus


_COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "阿里": ("阿里巴巴",),
    "阿里巴巴集团": ("阿里巴巴",),
    "腾讯公司": ("腾讯",),
    "字节": ("字节跳动",),
    "字节跳动公司": ("字节跳动",),
    "中信": ("中信集团", "中信证券"),
}

_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "简历修改": ("简历优化",),
    "简历润色": ("简历优化",),
    "模拟面试": ("面试辅导",),
    "mock interview": ("面试辅导",),
}

_INDUSTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "互联网": ("互联网与平台经济",),
    "信息技术": ("软件与信息技术",),
    "it": ("软件与信息技术",),
    "ai": ("人工智能、大数据与云计算",),
    "人工智能": ("人工智能、大数据与云计算",),
    "科技": ("软件与信息技术", "人工智能、大数据与云计算"),
}


def _lookup_key(raw_value: str) -> str:
    return unicodedata.normalize("NFKC", raw_value).strip().casefold()


def _normalize_from_aliases(
    raw_value: str,
    aliases: dict[str, tuple[str, ...]],
) -> NormalizationResult:
    candidates = aliases.get(_lookup_key(raw_value))
    if candidates is None:
        return NormalizationResult(raw_value, MappingStatus.UNMAPPED)
    if len(candidates) > 1:
        return NormalizationResult(None, MappingStatus.AMBIGUOUS)
    return NormalizationResult(candidates[0], MappingStatus.MAPPED)


def normalize_company_name(raw_name: str) -> NormalizationResult:
    """Normalize only explicitly safe company aliases, never legal full names."""

    return _normalize_from_aliases(raw_name, _COMPANY_ALIASES)


def normalize_skill(raw_skill: str) -> NormalizationResult:
    """Apply a small synonym map while allowing free-form skills."""

    return _normalize_from_aliases(raw_skill, _SKILL_ALIASES)


def normalize_industry(raw_industry: str) -> NormalizationResult:
    """Map safe aliases to the soft taxonomy without forcing unknown values."""

    lookup = _lookup_key(raw_industry)
    taxonomy_by_key = {
        _lookup_key(value): value for value in SOFT_INDUSTRY_TAXONOMY
    }
    if lookup in taxonomy_by_key:
        return NormalizationResult(taxonomy_by_key[lookup], MappingStatus.MAPPED)
    return _normalize_from_aliases(raw_industry, _INDUSTRY_ALIASES)


T = TypeVar("T")


def _stable_marker(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def deduplicate_items(
    items: Iterable[T],
    key: Callable[[T], Any] | None = None,
) -> list[T]:
    """Keep the first item for each stable deterministic key."""

    result: list[T] = []
    seen: set[str] = set()
    for item in items:
        marker = _stable_marker(key(item) if key else item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


__all__ = [
    "NormalizationResult",
    "deduplicate_items",
    "normalize_company_name",
    "normalize_industry",
    "normalize_skill",
]
