"""Alias loading and term expansion for mentor matching."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ALIAS_PATH = Path("configs") / "matching_aliases.json"


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", text)


@dataclass(frozen=True)
class AliasEntry:
    canonical: str
    aliases: tuple[str, ...]

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


class AliasIndex:
    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.entries: dict[str, list[AliasEntry]] = {}
        for category, rows in data.items():
            self.entries[category] = [
                AliasEntry(
                    canonical=str(row["canonical"]),
                    aliases=tuple(str(alias) for alias in row.get("aliases", [])),
                )
                for row in rows
            ]

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_ALIAS_PATH) -> "AliasIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload)

    def find_in_text(self, category: str, text: str) -> list[str]:
        normalized = normalize_text(text)
        found: list[str] = []
        seen: set[str] = set()
        for entry in self.entries.get(category, []):
            if any(normalize_text(term) in normalized for term in entry.terms):
                if entry.canonical not in seen:
                    seen.add(entry.canonical)
                    found.append(entry.canonical)
        return found

    def variants(self, category: str, term: str) -> list[str]:
        normalized_term = normalize_text(term)
        for entry in self.entries.get(category, []):
            if any(normalize_text(value) == normalized_term for value in entry.terms):
                return list(entry.terms)
        return [term]

    def canonical_for(self, category: str, term: str) -> str:
        normalized_term = normalize_text(term)
        for entry in self.entries.get(category, []):
            if any(normalize_text(value) == normalized_term for value in entry.terms):
                return entry.canonical
        return term


def unique_keep_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = normalize_text(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = [
    "AliasEntry",
    "AliasIndex",
    "DEFAULT_ALIAS_PATH",
    "normalize_text",
    "unique_keep_order",
]
