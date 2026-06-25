# Mentor Matching MVP Report

## 最新产品定义：Top 10 导师卡片

当前匹配 MVP 的目标不是给学员生成长推荐理由，而是返回 Top 10 导师卡片：

1. 把最可能合适的导师排到前面；
2. 返回前端可以直接展示的导师字段；
3. 内部保留 `score_breakdown` 和 `matched_signals`，方便后台调试、运营复核和后续调权重；
4. 不把 `recommendation_reason` 作为学员端核心输出。

### 学员端 display 字段

每个结果的 `display` 字段用于导师卡片展示：

- `rank`
- `mentor_id`
- `name`
- `gender`
- `city`
- `years_experience`
- `industries`
- `companies`
- `roles`
- `skills`
- `credentials`
- `education`
- `target_mentees`
- `highlights`
- `keywords`
- `summary`

注意：`companies` 只能理解为“资料中出现的相关公司/机构信号”。前端字段建议叫“相关公司/机构”或“相关公司信号”，不要叫“曾就职公司”。

### 内部 debug 字段

每个结果的 `debug` 字段用于调试和运营复核：

- `final_score`
- `score_breakdown`
- `matched_signals`
- `possible_gap`
- `profile_parse_result`
- `scoring_version`
- `recommendation_reason`

`possible_gap` 和 `recommendation_reason` 不作为学员端主要展示字段。若未来保留推荐理由，也只能用于内部，不允许出现未验证的“曾就职/任职过/供职/前员工/老东家”等公司关系表述。

### 当前排序策略

当前导师数量约 121 条，因此第一版保持简单：

- 全量扫描所有导师；
- 每个导师都计算分数；
- 按 `final_score` 排序；
- 默认返回 Top 10；
- 不使用 RRF；
- 不使用 LLM rerank；
- 不使用数据库；
- 不使用向量数据库。

### Scoring 设计

当前预留三类分数：

```text
final_score =
  0.50 * structured_score
+ 0.30 * raw_text_score
+ 0.20 * semantic_score
```

- `structured_score`：来自 simple extraction 字段匹配，例如 industries、companies、roles、skills、target_mentees、keywords。
- `raw_text_score`：来自 original_fields、summary、highlights、keywords 的 fallback 匹配。
- `semantic_score`：预留给后续 embedding 相似度。

当前没有接 embedding，因此 `semantic_score = null`，程序会按 active weights 只用 `structured_score` 和 `raw_text_score` 重新归一化。

内部仍保留六个业务维度分数，方便看清楚为什么某个导师被排上来：

- `company_match`
- `role_match`
- `skill_or_help_match`
- `target_mentee_match`
- `industry_match`
- `keyword_match`

### CLI 使用方式

```powershell
conda activate tutor
python match_mentors.py `
  --mentors outputs/simple_full_run/mentor_results.jsonl `
  --query "我是留学生，想找互联网产品经理，目标字节美团，需要简历优化和模拟面试" `
  --top-k 10 `
  --format both
```

Markdown 默认展示导师卡片字段，不展示长推荐理由、不展示 possible gap。若运营需要看分数，可加：

```powershell
python match_mentors.py --mentors outputs/simple_full_run/mentor_results.jsonl --query "..." --show-score
```

JSON 输出结构：

```json
{
  "student_profile": {},
  "results": [
    {
      "display": {
        "rank": 1,
        "mentor_id": "...",
        "name": "...",
        "gender": "...",
        "city": "...",
        "years_experience": 10,
        "industries": [],
        "companies": [],
        "roles": [],
        "skills": [],
        "credentials": [],
        "education": [],
        "target_mentees": [],
        "highlights": [],
        "keywords": [],
        "summary": "..."
      },
      "debug": {
        "final_score": 86.5,
        "score_breakdown": {},
        "matched_signals": {},
        "possible_gap": null,
        "profile_parse_result": {},
        "scoring_version": "matching-v1"
      }
    }
  ]
}
```

### 性能测试建议

第一版是离线内存扫描，没有实时模型调用。可以用同一份 `mentor_results.jsonl` 对多条 query 循环调用 `run_match(...)`，记录平均耗时、p95 耗时、Top 10 稳定性、query 解析置信度和 zero-score 结果比例。

121 条导师数据规模下，性能瓶颈不在扫描，而在 alias 表质量和 simple extraction 覆盖度。

### 后续接 embedding 的方式

后续如果要接 embedding，不需要改导师卡片输出结构，只需要：

1. 为导师生成 `mentor_search_text` 向量；
2. 为学员 query 或 `StudentProfile` 生成 query 向量；
3. 计算相似度归一化为 0-100；
4. 写入 `semantic_score`；
5. 让 `final_score` 使用完整 0.50 / 0.30 / 0.20 权重。

不建议在当前 121 条规模下优先引入向量数据库；可以先本地内存 embedding，确认收益后再考虑 pgvector/Elasticsearch/Milvus。

## 历史背景：第一版规则匹配说明

## 目标

第一版导师推荐不让客户查询实时等待 LLM。系统直接读取 simple mode 产出的 `mentor_results.jsonl`，在内存中扫描约 121 位导师，做规则召回、打分和解释，通常应是毫秒级路径。

## 新增文件

- `match_mentors.py`：离线 CLI 入口。
- `configs/matching_aliases.json`：公司、岗位、技能/帮助、学员阶段、行业 alias 表。
- `mentor_agent/matching/`：匹配 schema、alias 展开、学员画像抽取、导师索引、规则打分、输出格式化、可选 rerank guardrail。
- `tests/test_matching_*.py`：离线单元测试。

## 运行方式

```powershell
conda activate tutor
python match_mentors.py `
  --mentors outputs/simple_full_run_20260625_123834/mentor_results.jsonl `
  --query "我是留学生，想找互联网产品经理，目标字节美团，需要简历优化和模拟面试" `
  --top-k 5 `
  --format both
```

## 第一版链路

1. `StudentProfile`：用 alias 表和关键词规则解析学员 query。
2. `MentorDocument`：从 simple result 拼接结构化字段与 original_fields，作为召回文本。
3. 规则打分：对所有导师计算 company、role、skill/help、target_mentee、industry、keyword 六类分数。
4. 输出 `MatchResult`：包含 top-k、match_score、matched_signals、recommendation_reason、possible_gap。

## 打分权重

- company_match：30%
- role_match：20%
- skill_or_help_match：20%
- target_mentee_match：15%
- industry_match：10%
- keyword_match：5%

若 query 缺少某类需求，该类权重会从归一化分母中移除，避免因为学员没说某字段而误扣分。

## 防误判策略

- 公司字段只表达为“资料中出现相关公司/机构”，不说“曾就职”。
- simple extraction 漏抽时，规则会回退搜索 summary、highlights、keywords 和 original_fields 原文。
- LLM rerank 暂不默认启用；已提供 prompt 和 guardrail，要求理由只能来自 candidate card，并拒绝“曾就职/任职于”等未验证雇佣措辞。

## 当前限制

- StudentProfile 是规则抽取，不如 LLM 理解复杂意图强。
- alias 表仍然需要根据真实用户 query 持续补充。
- 当前没有向量召回；121 条导师数据足够直接内存扫，规模变大后再加 embedding。
- rerank 只保留接口和安全校验，不在默认 CLI 中调用，确保客户查询低延迟。

## 下一步建议

1. 用真实咨询 query 做 20-50 条离线评估，补 alias 表。
2. 若规则 top-k 解释足够稳定，先接入后端 API。
3. 对模糊 query 先返回推荐 + 追问，而不是阻塞等待 LLM。
4. 后续再加可选 LLM rerank，只对 Top 10 candidate cards 调用，并做超时降级。
