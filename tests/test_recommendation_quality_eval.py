import csv
import json
from pathlib import Path

from mentor_agent.matching.evaluation import (
    REVIEW_COLUMNS,
    expected_signal_coverage,
    load_eval_cases,
    load_gold_labels,
    run_quality_evaluation,
    supervised_metrics,
)
from mentor_agent.matching.formatter import build_match_result
from mentor_agent.matching.schemas import StudentProfile


def _write_aliases(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "companies": [
                    {"canonical": "字节跳动", "aliases": ["字节", "ByteDance"]},
                    {"canonical": "美团", "aliases": ["美团点评"]},
                ],
                "roles": [{"canonical": "产品经理", "aliases": ["产品", "PM"]}],
                "skills": [
                    {"canonical": "简历优化", "aliases": ["改简历"]},
                    {"canonical": "模拟面试", "aliases": ["面试辅导"]},
                ],
                "stages": [{"canonical": "应届生", "aliases": ["校招"]}],
                "industries": [{"canonical": "互联网", "aliases": ["大厂"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _mentor_result(
    mentor_id: str,
    *,
    companies: list[str],
    roles: list[str],
    skills: list[str],
    industries: list[str] | None = None,
    target_mentees: list[str] | None = None,
    summary: str = "互联网产品求职辅导",
) -> dict:
    suffix = mentor_id.rsplit(":", 1)[-1]
    return {
        "schema_version": "simple-v1",
        "prompt_version": "mentor-simple-v1",
        "mentor_id": mentor_id,
        "record_hash": f"{int(suffix):064x}",
        "source": {"file": "synthetic.xlsx", "sheet": "服务导师", "row": int(suffix) + 1},
        "original_fields": {
            "序号": int(suffix),
            "导师姓名": f"导师{suffix}",
            "性别": None,
            "城市": "上海",
            "职业年限": 8,
            "可辅导学员职级": "应届生 在职转型",
            "行业标签": "互联网",
            "从业经历": "资料中出现相关公司和产品项目",
            "背景经验": "擅长简历优化和模拟面试",
        },
        "extraction": {
            "industries": industries or ["互联网"],
            "companies": companies,
            "roles": roles,
            "skills": skills,
            "credentials": [],
            "education": [],
            "target_mentees": target_mentees or ["应届生"],
            "highlights": [],
            "keywords": [*companies, *roles, *skills],
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


def _write_mentors(path: Path) -> Path:
    rows = [
        _mentor_result(
            "service_mentor:1",
            companies=["字节跳动", "美团"],
            roles=["产品经理"],
            skills=["简历优化", "模拟面试"],
        ),
        _mentor_result(
            "service_mentor:2",
            companies=[],
            roles=["数据分析"],
            skills=["职业规划"],
            industries=["金融"],
            summary="金融数据分析辅导",
        ),
        _mentor_result(
            "service_mentor:3",
            companies=["腾讯"],
            roles=["运营"],
            skills=["面试辅导"],
        ),
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def _write_cases(path: Path) -> Path:
    payload = {
        "case_id": "case_001",
        "description": "应届生想找互联网产品经理，目标字节美团，需要简历优化和模拟面试",
        "student_profile": {
            "work_years": 0,
            "target_roles": ["产品经理"],
            "target_companies": ["字节跳动", "美团"],
            "target_industries": ["互联网"],
            "needed_help": ["简历优化", "模拟面试"],
            "current_stage": ["应届生"],
            "preferred_background": ["大厂"],
            "constraints": {"city": None, "gender": None, "seniority": None},
            "keywords": [],
        },
        "expected_signals": {
            "must_match_any": {
                "roles": ["产品经理"],
                "companies": ["字节跳动", "美团"],
                "skills": ["简历优化", "模拟面试"],
                "stage": ["应届生"],
            },
            "nice_to_have": {"industries": ["互联网"]},
        },
        "manual_judgement": None,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_eval_cases_and_gold_labels_load(tmp_path):
    cases_path = _write_cases(tmp_path / "cases.jsonl")
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "case_id": "case_001",
                "good_mentor_ids": [],
                "acceptable_mentor_ids": [],
                "bad_mentor_ids": [],
                "notes": "",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_eval_cases(cases_path)
    labels = load_gold_labels(gold_path)

    assert len(cases) == 1
    assert cases[0].student_profile.target_roles == ["产品经理"]
    assert labels["case_001"].good_mentor_ids == set()


def test_expected_signal_coverage_and_missing_signals():
    profile = StudentProfile(target_roles=["产品经理"], target_companies=["字节跳动"], needed_help=["简历优化"])
    from mentor_agent.matching.schemas import MentorCandidateCard

    card = MentorCandidateCard(
        mentor_id="service_mentor:1",
        name="导师1",
        industries=["互联网"],
        companies=["字节跳动"],
        roles=["产品经理"],
        skills=["简历优化"],
        target_mentees=["应届生"],
        keywords=["美团"],
        summary="产品求职辅导",
        rule_score=90,
        final_score=90,
    )
    result = build_match_result(query="", profile=profile, total_mentors=1, candidate_cards=[card], top_k=1)

    coverage = expected_signal_coverage(
        {"must_match_any": {"companies": ["字节跳动", "阿里"], "roles": ["产品经理"], "skills": ["简历优化"]}},
        result.results,
    )

    assert coverage["company_coverage"] == 0.5
    assert coverage["role_coverage"] == 1.0
    assert coverage["skill_coverage"] == 1.0
    assert coverage["missing_expected_signals"] == {"companies": ["阿里"]}


def test_supervised_metrics_hit_mrr_ndcg():
    from mentor_agent.matching.schemas import MentorCandidateCard
    from mentor_agent.matching.evaluation import GoldLabel

    profile = StudentProfile(target_roles=["产品经理"])
    cards = [
        MentorCandidateCard(mentor_id="m1", rule_score=90, final_score=90),
        MentorCandidateCard(mentor_id="m2", rule_score=80, final_score=80),
        MentorCandidateCard(mentor_id="m3", rule_score=70, final_score=70),
    ]
    result = build_match_result(query="", profile=profile, total_mentors=3, candidate_cards=cards, top_k=3)
    metrics = supervised_metrics(
        result,
        GoldLabel(
            case_id="case_001",
            good_mentor_ids={"m2"},
            acceptable_mentor_ids={"m3"},
            bad_mentor_ids={"m1"},
        ),
    )

    assert metrics["Hit@1"] == 0
    assert metrics["Hit@3"] == 1
    assert metrics["MRR"] == 0.5
    assert metrics["NDCG@10"] > 0
    assert metrics["bad_in_top10_count"] == 1


def test_quality_evaluation_outputs_csv_jsonl_report_without_original_fields(tmp_path):
    mentors = _write_mentors(tmp_path / "mentor_results.jsonl")
    cases = _write_cases(tmp_path / "cases.jsonl")
    aliases = _write_aliases(tmp_path / "aliases.json")
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps(
            {
                "case_id": "case_001",
                "good_mentor_ids": ["service_mentor:1"],
                "acceptable_mentor_ids": [],
                "bad_mentor_ids": [],
                "notes": "",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "eval_output"

    summary = run_quality_evaluation(
        mentors_path=mentors,
        cases_path=cases,
        aliases_path=aliases,
        output_dir=output_dir,
        top_k=2,
        semantic="none",
        gold_labels_path=gold,
    )

    assert summary["case_count"] == 1
    assert Path(summary["report_path"]).exists()
    for filename in [
        "recommendation_quality_report.md",
        "recommendation_quality_summary.csv",
        "recommendation_quality_details.jsonl",
        "recommendation_quality_review.csv",
    ]:
        assert (output_dir / filename).exists()
        text = (output_dir / filename).read_text(encoding="utf-8-sig" if filename.endswith(".csv") else "utf-8")
        assert "original_fields" not in text
        for unsafe in ["曾就职", "任职过", "供职", "前员工", "老东家"]:
            assert unsafe not in text

    with (output_dir / "recommendation_quality_review.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REVIEW_COLUMNS
        rows = list(reader)
    assert rows
    assert rows[0]["human_label"] == ""
    assert rows[0]["human_notes"] == ""

    detail = json.loads((output_dir / "recommendation_quality_details.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert detail["case_id"] == "case_001"
    assert "top_recommendations" in detail


def test_quality_evaluation_semantic_fake_runs(tmp_path):
    summary = run_quality_evaluation(
        mentors_path=_write_mentors(tmp_path / "mentor_results.jsonl"),
        cases_path=_write_cases(tmp_path / "cases.jsonl"),
        aliases_path=_write_aliases(tmp_path / "aliases.json"),
        output_dir=tmp_path / "eval_fake",
        top_k=2,
        semantic="fake",
    )

    assert summary["case_count"] == 1
    assert (tmp_path / "eval_fake" / "mentor_embeddings.json").exists()
