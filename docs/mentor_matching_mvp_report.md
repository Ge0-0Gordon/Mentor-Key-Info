# Mentor Matching MVP Report

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
