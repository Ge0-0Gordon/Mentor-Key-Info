"""Benchmark low-latency RecommendationEngine paths."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mentor_agent.matching import AliasIndex, RecommendationEngine
from mentor_agent.matching.aliases import DEFAULT_ALIAS_PATH
from mentor_agent.matching.schemas import StudentProfile


PROFILES = [
    StudentProfile(
        raw_query="留学生 互联网 产品经理 字节 美团 简历优化 模拟面试",
        work_years=0,
        target_roles=["产品经理"],
        target_companies=["字节跳动", "美团"],
        target_industries=["互联网"],
        needed_help=["简历优化", "模拟面试"],
        current_stage=["留学生", "应届生"],
        preferred_background=["大厂", "面试官"],
        keywords=["产品", "互联网"],
    ),
    StudentProfile(
        raw_query="应届生 阿里 腾讯 数据分析 职业规划 面试辅导",
        work_years=0,
        target_roles=["数据分析"],
        target_companies=["阿里", "腾讯"],
        target_industries=["互联网"],
        needed_help=["职业规划", "面试辅导"],
        current_stage=["应届生"],
        preferred_background=["大厂"],
        keywords=["数据", "分析"],
    ),
    StudentProfile(
        raw_query="在职 新能源车企 产品经理 蔚来 理想 小鹏 改简历",
        work_years=3,
        target_roles=["产品经理"],
        target_companies=["蔚来", "理想汽车", "小鹏汽车"],
        target_industries=["新能源汽车"],
        needed_help=["简历优化", "转行辅导"],
        current_stage=["在职"],
        preferred_background=["车企"],
        keywords=["新能源", "产品"],
    ),
    StudentProfile(
        raw_query="AI 大模型 互联网 人工智能 行业背景",
        work_years=2,
        target_roles=["AI产品经理"],
        target_companies=[],
        target_industries=["AI", "人工智能", "互联网"],
        needed_help=["职业规划"],
        current_stage=["在职"],
        preferred_background=["人工智能"],
        keywords=["大模型", "AIGC"],
    ),
    StudentProfile(
        raw_query="海归硕士 咨询 战略 case面试 职业规划",
        work_years=0,
        target_roles=["咨询", "战略"],
        target_companies=[],
        target_industries=["咨询"],
        needed_help=["case面试", "职业规划"],
        current_stage=["留学生", "应届生"],
        preferred_background=["咨询"],
        keywords=["case", "战略"],
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark recommendation engine latency.")
    parser.add_argument("--mentors", type=Path, default=Path("outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl"))
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIAS_PATH)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--semantic", choices=["none", "fake"], nargs="+", default=["none", "fake"])
    parser.add_argument("--output", type=Path, default=Path("outputs/reports/recommendation_benchmark_report.md"))
    return parser.parse_args()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def _run_mode(args: argparse.Namespace, semantic_mode: str) -> dict:
    started_load = time.perf_counter()
    engine = RecommendationEngine.from_jsonl(
        args.mentors,
        args.aliases,
        semantic_mode=semantic_mode,
        embedding_cache_path=Path("outputs/matching_embeddings/mentor_embeddings.json"),
    )
    cold_load_ms = int((time.perf_counter() - started_load) * 1000)
    latencies: list[float] = []
    last_result = None
    for idx in range(args.runs):
        profile = PROFILES[idx % len(PROFILES)]
        started = time.perf_counter()
        last_result = engine.recommend(profile, top_k=args.top_k)
        latencies.append((time.perf_counter() - started) * 1000)
    return {
        "semantic": semantic_mode,
        "mentor_count": len(engine.documents),
        "cold_load_ms": cold_load_ms,
        "runs": args.runs,
        "avg_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "p95_ms": _percentile(latencies, 95),
        "max_ms": max(latencies),
        "last_cache_hit": last_result.semantic.cache_hit_count if last_result else 0,
        "last_cache_miss": last_result.semantic.cache_miss_count if last_result else 0,
    }


def main() -> int:
    args = parse_args()
    if not args.mentors.exists():
        raise SystemExit(f"mentor results not found: {args.mentors}")
    AliasIndex.from_path(args.aliases)
    rows = [_run_mode(args, mode) for mode in args.semantic]
    lines = [
        "# Recommendation Benchmark",
        "",
        f"- mentors: `{args.mentors}`",
        f"- runs per mode: {args.runs}",
        "- LLM rerank: disabled",
        "",
        "| semantic | mentors | cold_load_ms | avg_ms | median_ms | p95_ms | max_ms | last_cache_hit | last_cache_miss |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['semantic']} | {row['mentor_count']} | {row['cold_load_ms']} | "
            f"{row['avg_ms']:.2f} | {row['median_ms']:.2f} | {row['p95_ms']:.2f} | "
            f"{row['max_ms']:.2f} | {row['last_cache_hit']} | {row['last_cache_miss']} |"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)
    for row in rows:
        print(
            f"{row['semantic']}: avg={row['avg_ms']:.2f}ms "
            f"median={row['median_ms']:.2f}ms p95={row['p95_ms']:.2f}ms max={row['max_ms']:.2f}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
