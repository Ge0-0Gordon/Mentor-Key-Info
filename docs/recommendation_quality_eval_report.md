# Recommendation Quality Evaluation Framework

## 目标

本阶段新增一套离线推荐质量评估测试框架，用来检查当前 `recommendation-v1` 排序结果是否合理。它只调用现有 `RecommendationEngine`，不修改主排序逻辑，不接 LLM，不接数据库，不接前端，也不默认启用 real semantic。

## 新增文件

- `eval/student_profiles_eval.jsonl`
  - 25 条结构化 `StudentProfile` 评估样本。
  - 覆盖互联网产品、数据分析/商业分析、金融、咨询/战略、HR/组织发展、新能源汽车、AI/大模型、模糊需求、城市/性别/资深度约束。
- `eval/gold_labels_template.jsonl`
  - gold label 人工标注模板。
  - 当前不编造导师 ID，`good_mentor_ids` / `acceptable_mentor_ids` / `bad_mentor_ids` 均为空。
- `mentor_agent/matching/evaluation.py`
  - 纯离线评估逻辑。
  - 负责 case/gold label 加载、weak coverage、supervised metrics、CSV/JSONL/Markdown 输出。
- `scripts/evaluate_recommendation_quality.py`
  - CLI 入口。
- `tests/test_recommendation_quality_eval.py`
  - 离线单元测试。

## 运行方式

推荐命令：

```powershell
python scripts/evaluate_recommendation_quality.py `
  --mentors outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --cases eval/student_profiles_eval.jsonl `
  --top-k 10 `
  --semantic none
```

指定输出目录：

```powershell
python scripts/evaluate_recommendation_quality.py `
  --mentors outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --cases eval/student_profiles_eval.jsonl `
  --gold-labels eval/gold_labels_template.jsonl `
  --top-k 10 `
  --semantic none `
  --output-dir outputs/recommendation_eval_YYYYMMDD_HHMMSS
```

离线 fake semantic 测试：

```powershell
python scripts/evaluate_recommendation_quality.py `
  --mentors outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --cases eval/student_profiles_eval.jsonl `
  --top-k 10 `
  --semantic fake
```

注意：CLI 只开放 `--semantic none/fake`。`real` 不在本评估脚本中默认启用，避免误接外部 embedding 服务。

## 输出文件

默认输出到：

```text
outputs/recommendation_eval_YYYYMMDD_HHMMSS/
  recommendation_quality_report.md
  recommendation_quality_summary.csv
  recommendation_quality_details.jsonl
  recommendation_quality_review.csv
```

这些输出位于 `outputs/` 下，默认不提交 Git。

## Weak evaluation 指标

在没有人工 gold labels 前，脚本先做弱评估。每个 case 统计：

- `top1_score`
- `top3_avg_score`
- `top10_avg_score`
- `top10_min_score`
- `zero_score_count`
- `top10_company_hit_count`
- `top10_role_hit_count`
- `top10_skill_hit_count`
- `top10_stage_hit_count`
- `top10_industry_hit_count`
- `top10_expected_signal_coverage`
- `top10_distinct_industries`
- `top10_distinct_roles`
- `latency_ms`

`expected_signal_coverage` 会检查 Top10 的 display 字段、matched signals、keywords、summary 是否覆盖 case 中定义的期望信号。

重要：weak evaluation 只是辅助排查 alias、标签覆盖和打分问题，不代表真实推荐准确率。

## 人工 review CSV

`recommendation_quality_review.csv` 每条 Top10 推荐一行，包含：

- `case_id`
- `rank`
- `mentor_id`
- `name`
- `final_score`
- `company_match`
- `role_match`
- `skill_match`
- `industry_match`
- `stage_match`
- `years_match`
- `semantic_match`
- `industries`
- `companies`
- `roles`
- `skills`
- `target_mentees`
- `summary`
- `auto_signal_hits`
- `human_label`
- `human_notes`

`human_label` 默认留空，供业务方后续填写：

```text
good / acceptable / bad
```

## Gold labels 指标

如果提供 `--gold-labels`，且某个 case 有非空 `good_mentor_ids` 或 `acceptable_mentor_ids`，脚本会计算：

- `Hit@1`
- `Hit@3`
- `Hit@5`
- `Hit@10`
- `MRR`
- `NDCG@10`
- `bad_in_top10_count`

定义：

- good = 2 分
- acceptable = 1 分
- unknown = 0 分
- bad 单独统计进入 Top10 的数量

当前模板不含任何导师 ID，避免伪造金标准。

## 安全限制

评估输出不包含完整 `original_fields`，也不输出完整导师原文。

输出中避免以下未经验证的公司关系表述：

- 曾就职
- 任职过
- 供职
- 前员工
- 老东家

导师 `companies` 仍然只表示“相关公司/机构信号”，不是雇佣关系。

## 诊断逻辑

报告会给出简单诊断：

- expected signal 未覆盖时，提示可能是 alias gap 或导师数据缺口。
- Top10 有 0 分导师时，提示人工 review。
- summary CSV 保留 distinct industry/role 数量，方便观察多样性。

脚本只给建议，不自动修改 alias，也不自动改权重。

## 测试

运行：

```powershell
python -m pytest -q
```

测试覆盖：

- eval cases 加载。
- gold labels 模板加载。
- expected signal coverage 与 missing signals。
- review CSV 字段完整。
- details JSONL 字段完整。
- 无 gold labels 时不报错。
- 有 gold labels 时 Hit@K / MRR / NDCG。
- 输出不包含完整 `original_fields`。
- 输出不包含禁用表述。
- fake mentor data 上能运行。
- `semantic none` / `semantic fake` 都能运行。

## 下一步建议

1. 先人工 review `recommendation_quality_review.csv`，给每个 case 的 Top10 标 `good / acceptable / bad`。
2. 基于人工标注计算 Hit@K / MRR / NDCG，再决定是否调权重。
3. 对低 coverage case，优先补 alias 和导师 extraction 数据，而不是立刻调权重。
4. 如果 weak coverage 仍然不足，再测试 real semantic。
5. 后续可以增加 mentor_quality / availability，但不要在没有业务标签前过早复杂化。
