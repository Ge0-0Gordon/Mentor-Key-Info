from mentor_agent.matching.aliases import AliasIndex, normalize_text


def test_alias_index_expands_and_finds_terms(tmp_path):
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(
        """
        {
          "companies": [{"canonical": "字节跳动", "aliases": ["字节", "ByteDance"]}],
          "roles": [{"canonical": "产品经理", "aliases": ["PM", "产品"]}]
        }
        """,
        encoding="utf-8",
    )
    aliases = AliasIndex.from_path(alias_path)

    assert aliases.find_in_text("companies", "目标 ByteDance 产品岗") == ["字节跳动"]
    assert aliases.canonical_for("roles", "PM") == "产品经理"
    assert "ByteDance" in aliases.variants("companies", "字节跳动")


def test_normalize_text_is_width_case_and_space_insensitive():
    assert normalize_text(" Ｂｙｔｅ Dance\n") == "bytedance"
