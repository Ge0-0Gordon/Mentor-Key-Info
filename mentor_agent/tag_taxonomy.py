"""Parse the standard position and industry taxonomy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


_POSITION_PATTERN = re.compile(r"^-\s*(.+)$")


class TagTaxonomyError(ValueError):
    """Raised when the taxonomy file does not satisfy the expected structure."""


@dataclass(frozen=True)
class TagTaxonomy:
    position_groups: dict[str, tuple[str, ...]]
    position_tags: tuple[str, ...]
    industry_tags: tuple[str, ...]
    source_path: Path
    taxonomy_hash: str


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _canonical_hash(
    position_groups: dict[str, tuple[str, ...]],
    position_tags: tuple[str, ...],
    industry_tags: tuple[str, ...],
) -> str:
    canonical = {
        "position_groups": [
            {"group": group, "tags": list(tags)}
            for group, tags in position_groups.items()
        ],
        "position_tags": list(position_tags),
        "industry_tags": list(industry_tags),
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_tag_taxonomy(path: str | Path) -> TagTaxonomy:
    """Load one taxonomy file and fail fast on structural ambiguity."""

    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"taxonomy file does not exist: {source_path}")

    lines = source_path.read_text(encoding="utf-8-sig").splitlines()
    position_indexes = [
        index
        for index, line in enumerate(lines)
        if _POSITION_PATTERN.fullmatch(line.strip())
    ]
    if not position_indexes:
        raise TagTaxonomyError("taxonomy must contain at least one position tag")

    last_position_index = position_indexes[-1]
    position_groups_lists: dict[str, list[str]] = {}
    current_group: str | None = None
    position_tags_list: list[str] = []

    for line_number, raw_line in enumerate(lines[: last_position_index + 1], start=1):
        line = raw_line.strip()
        if not line:
            continue
        position_match = _POSITION_PATTERN.fullmatch(line)
        if position_match:
            tag = position_match.group(1).strip()
            if not tag:
                raise TagTaxonomyError(
                    f"empty position tag at line {line_number}"
                )
            if current_group is None:
                raise TagTaxonomyError(
                    f"position tag before any group at line {line_number}"
                )
            position_groups_lists[current_group].append(tag)
            position_tags_list.append(tag)
            continue

        current_group = line
        position_groups_lists.setdefault(current_group, [])

    empty_groups = [
        group for group, tags in position_groups_lists.items() if not tags
    ]
    if empty_groups:
        raise TagTaxonomyError(
            "position group has no tags: " + ", ".join(empty_groups)
        )

    industry_tags_list: list[str] = []
    for line_number, raw_line in enumerate(
        lines[last_position_index + 1 :],
        start=last_position_index + 2,
    ):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-"):
            raise TagTaxonomyError(
                f"position-style item found in industry section at line {line_number}"
            )
        industry_tags_list.append(line)

    position_tags = _unique(position_tags_list)
    if not position_tags:
        raise TagTaxonomyError("taxonomy must contain at least one position tag")
    industry_tags = _unique(industry_tags_list)
    if not industry_tags:
        raise TagTaxonomyError("taxonomy must contain at least one industry tag")

    position_groups = {
        group: tuple(tags) for group, tags in position_groups_lists.items()
    }
    return TagTaxonomy(
        position_groups=position_groups,
        position_tags=position_tags,
        industry_tags=industry_tags,
        source_path=source_path,
        taxonomy_hash=_canonical_hash(
            position_groups,
            position_tags,
            industry_tags,
        ),
    )


__all__ = ["TagTaxonomy", "TagTaxonomyError", "load_tag_taxonomy"]
