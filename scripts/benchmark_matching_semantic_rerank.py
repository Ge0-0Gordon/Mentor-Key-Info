"""Benchmark rule, fake semantic, and optional LLM rerank matching paths."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from match_mentors import run_match


QUERIES = [
    "我是留学生，想找互联网产品经理，目标字节美团，需要简历优化和模拟面试",
    "我是应届生，想投阿里腾讯的数据分析岗位，需要职业规划和面试辅导",
    "我在职想转行做新能源车企产品经理，目标蔚来理想小鹏，希望导师帮我改简历",
    "我想找AI大模型相关岗位，希望导师有互联网或人工智能行业背景",
    "我是海归硕士，想做咨询或战略岗，需要case面试和职业规划",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark matching semantic and rerank modes.")
    parser.add_argument(
        "--mentors",
        type=Path,
        default=Path("outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl"),
    )
    parser.add_argument("--output", type=Path, default=Path("outputs/reports/matching_semantic_rerank_report.md"))
    parser.add_argument("--skip-llm", action="store_true", help="Skip real LLM rerank benchmark.")
    return parser.parse_args()


def _top10(result) -> list[dict]:
    rows = []
    for item in result.results[:10]:
        rows.append(
            {
                "rank": item.display.rank,
                "mentor_id": item.display.mentor_id,
                "name": item.display.name,
                "final_score": item.debug.final_score,
                "structured": item.debug.score_breakdown.structured_score,
                "raw_text": item.debug.score_breakdown.raw_text_score,
                "semantic": item.debug.score_breakdown.semantic_score,
                "rule_rank": item.debug.rule_rank,
                "llm_rank": item.debug.llm_rank,
            }
        )
    return rows


def _run_case(label: str, mentors: Path, query: str, **kwargs) -> dict:
    started = time.perf_counter()
    try:
        result, _ = run_match(mentors_path=mentors, query=query, top_k=10, **kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "label": label,
            "ok": True,
            "latency_ms": latency_ms,
            "result": result,
            "top10": _top10(result),
        }
    except Exception as exc:  # noqa: BLE001 - benchmark should keep going
        return {
            "label": label,
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": f"{exc.__class__.__name__}: {str(exc)[:160]}",
        }


def _top_table(rows: list[dict]) -> list[str]:
    lines = [
        "| rank | mentor_id | name | final | structured | raw_text | semantic | rule_rank | llm_rank |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        semantic = "-" if row["semantic"] is None else f"{row['semantic']:.1f}"
        llm_rank = "-" if row["llm_rank"] is None else row["llm_rank"]
        lines.append(
            f"| {row['rank']} | {row['mentor_id']} | {row['name'] or '-'} | "
            f"{row['final_score']:.1f} | {row['structured']:.1f} | "
            f"{row['raw_text']:.1f} | {semantic} | {row['rule_rank'] or '-'} | {llm_rank} |"
        )
    return lines


def main() -> int:
    args = parse_args()
    if not args.mentors.exists():
        raise SystemExit(f"mentor results not found: {args.mentors}")

    lines = [
        "# Matching Semantic/Rerank Benchmark",
        "",
        f"- mentors: `{args.mentors}`",
        "- no mentor original text is printed",
        "",
    ]

    for idx, query in enumerate(QUERIES, start=1):
        lines.extend([f"## Query {idx}", "", query, ""])
        cases = [
            _run_case("A baseline: semantic none, rerank none", args.mentors, query, semantic="none", rerank="none"),
            _run_case(
                "B fake semantic, rerank none",
                args.mentors,
                query,
                semantic="fake",
                rerank="none",
            ),
        ]
        if not args.skip_llm:
            cases.append(
                _run_case(
                    "C fake semantic + LLM rerank Top20",
                    args.mentors,
                    query,
                    semantic="fake",
                    rerank="llm",
                    rerank_candidate_k=20,
                    rerank_timeout=8,
                )
            )

        for case in cases:
            lines.extend([f"### {case['label']}", ""])
            lines.append(f"- ok: {case['ok']}")
            lines.append(f"- latency_ms: {case['latency_ms']}")
            if not case["ok"]:
                lines.append(f"- error: {case['error']}")
                lines.append("")
                continue
            result = case["result"]
            lines.append(
                f"- semantic: enabled={result.semantic.enabled}, method={result.semantic.method}, "
                f"cache_hit={result.semantic.cache_hit_count}, cache_miss={result.semantic.cache_miss_count}"
            )
            lines.append(
                f"- rerank: enabled={result.rerank.enabled}, success={result.rerank.success}, "
                f"fallback={result.rerank.fallback_used}, latency_ms={result.rerank.latency_ms}, "
                f"error={result.rerank.error_message}"
            )
            lines.extend(["", *_top_table(case["top10"]), ""])

        lines.extend(
            [
                "Manual quality note: review whether semantic adds useful near-match mentors without pushing weak company-only signals too high.",
                "",
            ]
        )

    lines.extend(
        [
            "## Recommendation",
            "",
            "- Default semantic_score: recommend enabling only after fake/real semantic quality is reviewed; fake is deterministic but not a true embedding model.",
            "- Default LLM rerank: not recommended for realtime by default; keep optional because timeout/fallback is expected.",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
