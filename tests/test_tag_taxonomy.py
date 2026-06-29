"""Tests for the closed standard-tag taxonomy."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentor_agent.tag_taxonomy import TagTaxonomyError, load_tag_taxonomy


TAXONOMY_PATH = Path("configs/职位类型_2.txt")


def test_repository_taxonomy_parses_expected_pools() -> None:
    taxonomy = load_tag_taxonomy(TAXONOMY_PATH)

    assert len(taxonomy.position_groups) == 17
    assert len(taxonomy.position_tags) == 64
    assert len(taxonomy.industry_tags) == 11
    assert "互联网/AI" not in taxonomy.position_tags
    assert "产品" not in taxonomy.position_tags
    assert "人工智能" in taxonomy.position_tags
    assert "产品经理" in taxonomy.position_tags
    assert "AI/互联网/IT" in taxonomy.industry_tags
    assert taxonomy.position_groups["生产制造"].count("电气自动化") == 1
    assert "电气自动化" in taxonomy.position_groups["电子/电气/通信"]


def test_canonical_hash_ignores_bom_newlines_and_trailing_blanks(
    tmp_path: Path,
) -> None:
    content = "技术\n- 人工智能\n\nAI/互联网/IT\n"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text(content, encoding="utf-8")
    second.write_bytes(("\ufeff" + content.replace("\n", "\r\n") + "\r\n").encode("utf-8"))

    assert (
        load_tag_taxonomy(first).taxonomy_hash
        == load_tag_taxonomy(second).taxonomy_hash
    )


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("技术\nAI/互联网/IT\n", "position"),
        ("技术\n- 人工智能\n", "industry"),
        ("- 人工智能\n\nAI/互联网/IT\n", "before any group"),
        ("技术\n- 人工智能\n\nAI/互联网/IT\n- 错误项\n", "industry"),
    ],
)
def test_invalid_taxonomy_fails_fast(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    path = tmp_path / "invalid.txt"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(TagTaxonomyError, match=message):
        load_tag_taxonomy(path)
