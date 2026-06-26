import json

from match_mentors import run_match
from mentor_agent.matching import AliasIndex, RecommendationEngine, load_mentor_documents
from mentor_agent.matching.embeddings import EmbeddingCache, cosine_similarity, fake_hash_embedding
from mentor_agent.matching.scorer import SemanticContext, build_student_search_text, rank_candidates
from mentor_agent.matching.student_profile import extract_student_profile


def _write_aliases(path):
    path.write_text(
        json.dumps(
            {
                "companies": [{"canonical": "字节跳动", "aliases": ["字节"]}],
                "roles": [{"canonical": "产品经理", "aliases": ["产品"]}],
                "skills": [{"canonical": "简历优化", "aliases": ["改简历"]}],
                "stages": [{"canonical": "留学生", "aliases": ["海归"]}],
                "industries": [{"canonical": "互联网", "aliases": ["大厂"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _row(mentor_id="service_mentor:1", record_hash=None, summary="互联网产品简历优化"):
    idx = mentor_id.split(":")[-1]
    return {
        "schema_version": "simple-v1",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": mentor_id,
        "record_hash": record_hash or (idx * 64)[:64],
        "source": {"file": "synthetic.xlsx", "sheet": "服务导师", "row": int(idx) + 1},
        "original_fields": {
            "序号": int(idx),
            "导师姓名": f"导师{idx}",
            "性别": None,
            "城市": "上海",
            "职业年限": 8,
            "可辅导学员职级": "留学生 应届生",
            "行业标签": "互联网",
            "从业经历": "资料中出现字节跳动产品项目。",
            "背景经验": "擅长简历优化和模拟面试。",
        },
        "extraction": {
            "industries": ["互联网"],
            "companies": ["字节跳动"],
            "roles": ["产品经理"],
            "skills": ["简历优化"],
            "credentials": [],
            "education": [],
            "target_mentees": ["留学生"],
            "highlights": [],
            "keywords": ["字节", "产品", "简历优化"],
            "summary": summary,
        },
        "processing": {
            "status": "success",
            "attempt_count": 1,
            "processed_at": "2026-06-25T00:00:00Z",
            "model_service_name": "fake",
            "model_name": "fake",
            "latency_ms": 1,
        },
    }


def _write_results(path, rows):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_fake_embedding_is_deterministic_and_cosine_works():
    left = fake_hash_embedding("互联网 产品 简历")
    right = fake_hash_embedding("互联网 产品 简历")
    other = fake_hash_embedding("金融 投行")

    assert left == right
    assert cosine_similarity(left, right) > cosine_similarity(left, other)


def test_embedding_cache_hits_and_record_hash_miss(tmp_path):
    cache_path = tmp_path / "embeddings.json"
    cache = EmbeddingCache(cache_path)
    cache.set("service_mentor:1", "hash-a", "fake-hash-v1", [1.0, 0.0])
    cache.save()

    loaded = EmbeddingCache(cache_path)
    assert loaded.get("service_mentor:1", "hash-a", "fake-hash-v1") == [1.0, 0.0]
    assert loaded.stats.hit_count == 1
    assert loaded.get("service_mentor:1", "hash-b", "fake-hash-v1") is None
    assert loaded.stats.miss_count == 1


def test_semantic_score_enters_final_score_and_none_normalizes(tmp_path):
    aliases = AliasIndex.from_path(_write_aliases(tmp_path / "aliases.json"))
    result_path = _write_results(tmp_path / "mentor_results.jsonl", [_row()])
    document = load_mentor_documents(result_path)[0]
    profile = extract_student_profile("留学生想找字节产品经理，改简历", aliases)

    none_card = rank_candidates([document], profile, aliases, candidate_pool_size=1)[0]
    assert none_card.semantic_score is None
    assert none_card.score_breakdown.semantic_match is None
    assert none_card.final_score == none_card.score_breakdown.relevance_score

    cache = EmbeddingCache(tmp_path / "cache.json")
    context = SemanticContext(
        method="fake",
        embedding_model="fake-hash-v1",
        cache=cache,
        query_embedding=fake_hash_embedding(build_student_search_text(profile)),
    )
    semantic_card = rank_candidates([document], profile, aliases, candidate_pool_size=1, semantic_context=context)[0]
    assert semantic_card.semantic_score is not None
    assert semantic_card.score_breakdown.semantic_score == semantic_card.semantic_score


def test_run_match_semantic_fake_outputs_metadata_and_cache(tmp_path):
    aliases = _write_aliases(tmp_path / "aliases.json")
    mentors = _write_results(tmp_path / "mentor_results.jsonl", [_row("service_mentor:1"), _row("service_mentor:2")])
    cache_path = tmp_path / "mentor_embeddings.json"

    result, markdown = run_match(
        mentors_path=mentors,
        query="留学生想找字节产品经理，改简历",
        top_k=2,
        aliases_path=aliases,
        semantic="fake",
        embedding_cache_path=cache_path,
    )

    assert result.semantic.enabled is True
    assert result.semantic.method == "fake"
    assert result.semantic.cache_miss_count == 2
    assert result.results[0].debug.score_breakdown.semantic_score is not None
    assert cache_path.exists()

    second, _ = run_match(
        mentors_path=mentors,
        query="留学生想找字节产品经理，改简历",
        top_k=2,
        aliases_path=aliases,
        semantic="fake",
        embedding_cache_path=cache_path,
    )
    assert second.semantic.cache_hit_count == 2
    assert "semantic" not in markdown


def test_recommendation_engine_returns_all_mentors_and_years_match(tmp_path):
    aliases = _write_aliases(tmp_path / "aliases.json")
    mentors = _write_results(tmp_path / "mentor_results.jsonl", [_row("service_mentor:1"), _row("service_mentor:2")])
    engine = RecommendationEngine.from_jsonl(mentors, aliases, semantic_mode="none")
    profile = extract_student_profile("留学生想找字节产品经理，改简历", engine.aliases)
    profile.work_years = 3

    result = engine.recommend(profile, top_k=1)

    assert result.total_mentors == 2
    assert len(result.results) == 2
    assert result.results[0].display.is_recommended is True
    assert result.results[1].display.is_recommended is False
    assert result.results[0].debug.score_breakdown.years_match > 0
