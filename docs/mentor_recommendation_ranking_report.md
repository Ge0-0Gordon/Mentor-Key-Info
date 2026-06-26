# Mentor Recommendation Ranking Report

## Latest business definition

This stage turns matching into a low-latency student-profile to mentor-ranking
engine. It is not a realtime LLM recommendation system. The realtime path reads
pre-extracted simple mentor profiles, scores every mentor in memory, sorts all
mentors by `final_score`, and marks the Top N as recommended.

The student-facing output is mentor cards. Internal `debug` fields are kept for
operations and evaluation, but long recommendation reasons are not part of the
student-facing display.

## Why realtime does not use LLM

LLM rerank is too slow and unstable for the default query path. Prior online
tests showed even compact rerank can timeout around 8 seconds or take tens of
seconds depending on model and candidate count. The realtime product target is
under 5 seconds, ideally much lower, so the default path is deterministic local
ranking.

LLM rerank remains available as an optional offline/backend enhancement:

```powershell
python match_mentors.py `
  --mentors outputs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --query "..." `
  --semantic none `
  --rerank llm `
  --rerank-candidate-k 20 `
  --rerank-timeout 8
```

## Data structures

Mentors are loaded from simple-mode `mentor_results.jsonl` into in-memory
`MentorDocument` records. Each document keeps:

- original `SimpleMentorResult`
- `search_text` for deterministic fallback matching
- `mentor_search_text` for semantic matching
- selected original fields for internal search only

Full `original_fields` are not printed in logs or reports.

Companies are treated only as related company/institution signals, not verified
employment history.

## StudentProfile input

Two input modes are supported:

1. Development query mode:

```powershell
python match_mentors.py `
  --mentors outputs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --query "我是留学生，想找互联网产品经理，目标字节美团，需要简历优化和模拟面试"
```

2. Structured profile JSON:

```powershell
python match_mentors.py `
  --mentors outputs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --student-profile-json inputs/student_profile.json `
  --top-k 10 `
  --semantic none `
  --rerank none `
  --format both
```

Example profile:

```json
{
  "student_profile": {
    "work_years": 0,
    "target_roles": ["产品经理"],
    "target_companies": ["字节跳动", "美团"],
    "target_industries": ["互联网"],
    "needed_help": ["简历优化", "模拟面试"],
    "current_stage": ["留学生", "应届生"],
    "preferred_background": ["大厂", "面试官"],
    "constraints": {
      "city": null,
      "gender": null,
      "seniority": null
    },
    "keywords": []
  }
}
```

## Scoring formula

`recommendation-v1` uses interpretable weighted scoring:

```text
relevance_score =
  0.25 * company_match
+ 0.20 * role_match
+ 0.20 * skill_match
+ 0.10 * industry_match
+ 0.10 * stage_match
+ 0.05 * years_match
+ 0.10 * semantic_match
```

If `semantic_match` is unavailable, active weights are normalized over the
available dimensions. Final score is:

```text
final_score = relevance_score * availability_factor * mentor_quality_factor
```

V1 defaults:

```text
availability_factor = 1.0
mentor_quality_factor = 1.0
```

Debug keeps business dimensions, legacy structured/raw text helper scores, and
matched signals.

## Semantic score

Semantic matching is optional:

- `--semantic none`: default, no embedding work.
- `--semantic fake`: deterministic local hash embeddings for tests and offline
  experiments.
- `--semantic real`: reserved for a future real embedding provider.

The fake/real interface uses:

```text
mentor_search_text -> mentor embedding
student_search_text -> student embedding
cosine similarity -> semantic_match 0-100
```

Mentor embeddings are cached at:

```text
outputs/matching_embeddings/mentor_embeddings.json
```

Cache key:

```text
mentor_id + record_hash + embedding_model
```

## Output structure

JSON output includes:

- `student_profile`
- `recommendation`
- `all_mentors`
- `filters`
- backward-compatible `results`
- optional `semantic` and `rerank` metadata

`all_mentors` returns every mentor sorted by `final_score`; Top N mentors have
`display.is_recommended=true`.

Filters are generated from all mentor display fields:

- companies
- roles
- industries
- skills
- cities

## RecommendationEngine

Implemented:

```python
engine = RecommendationEngine.from_jsonl(
    mentors_path,
    aliases_path,
    semantic_mode="none",
)

result = engine.recommend(student_profile, top_k=10)
```

This preloads mentor data and aliases for repeated online-style calls.

## Benchmark

Command:

```powershell
python scripts/benchmark_recommendation.py
```

Report:

```text
outputs/recommendation_benchmark_report.md
```

Observed on the current 121-mentor simple result file, 100 warm calls per mode:

| semantic | avg_ms | median_ms | p95_ms | max_ms |
|---|---:|---:|---:|---:|
| none | 258.13 | 246.98 | 299.33 | 312.14 |
| fake | 263.18 | 252.64 | 300.53 | 304.80 |

This is well under the 5-second product requirement. It is slightly above the
ideal 200ms target, so future optimization can cache candidate display/debug
construction if needed.

## Current limits

- Fake semantic is deterministic but not a real embedding model.
- `mentor_quality` and `availability` are default factors only.
- Query parser remains a development fallback; production should pass structured
  `StudentProfile`.
- No database, API service, frontend, vector DB, or default LLM rerank is added.

## Future upgrades

- Add a real embedding provider after quality validation.
- Add mentor availability and mentor quality signals.
- Learn from clicks, bookings, and feedback.
- Train a lightweight ranking model when enough labeled data exists.
- Keep LLM rerank for offline/backend evaluation, not realtime default ranking.
