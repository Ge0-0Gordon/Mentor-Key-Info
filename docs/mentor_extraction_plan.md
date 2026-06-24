# 导师关键信息识别 Agent 技术方案

## 1. 文档目的

本文档定义“导师关键信息识别 Agent”第一版（V1）的业务边界、数据契约、抽取规则、证据校验、批处理流程、文件职责、输出格式和阶段式开发计划。

V1 的目标是：在不改写原始导师资料、不编造缺失信息的前提下，将单个导师的结构化字段和长文本字段转成稳定、可审计、便于检索与人工复核的 JSON 结果；Excel 批量处理由独立脚本逐行调用本地 Agent 接口完成。

本项目当前只做本地开发和测试：

- 保留现有 AgentRun OpenAI-compatible 接口；
- Agent 每次只处理一个导师；
- 批处理脚本负责读取 Excel、断点续跑和导出；
- 不接数据库；
- 不启用沙盒；
- 不覆盖原始 Excel；
- 只使用已授权的 AgentRun 模型服务。

## 2. 已确认的核心原则

### 2.1 原文优先

- 最终结果必须完整保留 Excel 的九个原始字段。
- 所有语义抽取项尽量提供原文 evidence。
- 不确定的信息不补全、不扩写、不根据常识猜测。
- 标准化失败时不得丢弃原始抽取结果。

### 2.2 轻度标准化

- 行业分类是 soft taxonomy，不是硬枚举。
- 技能名称允许自由抽取，只做轻度同义归一。
- 公司只做常见简称和别名归一，不补工商全称。
- 所有可标准化对象尽量同时保存 raw、normalized 和 mapping_status。

### 2.3 关系严格

组织关系必须区分：

- `employer`：原文明确表达任职、就职、曾在、担任某岗位等雇佣关系；
- `client`：客户、服务对象；
- `project`：参与或交付的项目所涉及组织；
- `partner`：合作方、生态伙伴；
- `unknown`：组织被提及，但关系证据不足。

只有 `relationship == "employer"` 的组织可以被业务侧视为“曾就职公司”。“服务过”“合作过”“客户包括”不能计入曾就职公司。

### 2.4 V1 强校验保持克制

Pydantic Schema 可以覆盖完整业务结构，但 V1 只强校验以下核心约束：

- 输出是合法 JSON；
- confidence 只能是 `high / medium / low`；
- organization relationship 只能使用规定值；
- mapping_status 只能是 `mapped / unmapped / ambiguous`；
- 需要标准化的核心项包含 raw/normalized 字段；
- 语义抽取项包含 evidence；
- evidence 能通过严格或宽松原文匹配。

`career_highlights.metrics`、`industry_derivation`、时间范围等复杂字段在 V1 中允许为空或缺省，不作为整条记录失败的原因。

## 3. 总体架构

```text
原始 Excel
  -> batch_extract.py 读取并校验单行
  -> 构造 MentorInput 与 record_hash
  -> 通过 message.content 调用本地 OpenAI-compatible 接口
  -> Agent 生成 MentorExtraction
  -> Pydantic 核心结构校验
  -> evidence 严格/宽松校验
  -> 确定性别名归一、去重、质量告警
  -> 组装 MentorResult
  -> 成功 checkpoint / failed_rows.jsonl
  -> 最终 mentor_results.jsonl
  -> 新的多 Sheet 人工审阅 Excel
```

系统分为三个数据层：

1. `MentorInput`：由程序从 Excel 确定性构造；
2. `MentorExtraction`：由模型负责生成的语义抽取结果；
3. `MentorResult`：程序将输入、抽取结果、证据校验、质量问题和处理元数据组装后的最终结果。

行号、文件名、哈希、处理时间、重试次数等确定性数据不得交给模型生成。

## 4. Pydantic Schema 草案

### 4.1 公共枚举

#### Confidence

- `high`
- `medium`
- `low`

置信度规则：

- `high`：原文明确表达实体及其关系，且 evidence 直接支持；
- `medium`：实体明确，但关系边界或轻度归一存在一定歧义；
- `low`：原文支持较弱但仍可定位，不包含纯推测。

纯推测结果不能通过设置 `low` 保留。

#### MappingStatus

- `mapped`：已安全映射到规范表达；
- `unmapped`：未找到安全映射，保留原始表达；
- `ambiguous`：存在多个合理映射或上下文不足，不能唯一归一。

推荐取值规则：

- `mapped` 时 `normalized_value` 应为可信规范值；
- `unmapped` 时 `normalized_value` 可以是仅去除首尾空白后的 raw，也可以为 `null`；消费者必须结合 mapping_status 判断；
- `ambiguous` 时原则上将 `normalized_value` 设为 `null`，避免把候选项伪装成确定结论。

#### OrganizationRelationship

- `employer`
- `client`
- `project`
- `partner`
- `unknown`

#### EmploymentStatus

- `current`
- `former`
- `unknown`

#### CredentialCategory

- `professional_certification`
- `training_certificate`
- `coach_certificate`
- `teaching_certificate`
- `award`
- `other`

#### CredentialStatus

- `held`
- `in_progress`
- `candidate`
- `unknown`

#### SkillCategory

技能名称不使用硬枚举，但允许用以下大类帮助检索：

- `domain_expertise`
- `functional_skill`
- `management_leadership`
- `coaching_mentoring`
- `job_search_guidance`
- `technical_tool`
- `language_communication`
- `other`

### 4.2 Evidence

每条 evidence 至少包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_field` | `str` | evidence 所属的原始 Excel 字段 |
| `quote` | `str` | 对应字段中的连续原文片段 |
| `match_type` | `strict / loose / invalid / null` | 由程序校验后填写；模型输出阶段可为 null |

允许的 source_field：

- `导师姓名`
- `性别`
- `城市`
- `职业年限`
- `可辅导学员职级`
- `行业标签`
- `从业经历`
- `背景经验`

模型只负责输出 `source_field` 和 `quote`，`match_type` 必须由程序计算。

### 4.3 MentorInput

`MentorInput` 由 `batch_extract.py` 构造：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `task` | `str` | 是 | 固定为 `extract_mentor_key_info` |
| `input_schema_version` | `str` | 是 | V1 固定为 `1.0` |
| `mentor_id` | `str` | 是 | 建议格式 `service_mentor:{序号}` |
| `record_hash` | `str` | 是 | 九个原始字段规范序列化后的 SHA-256 |
| `source_file` | `str` | 是 | 只保存文件名，不保存绝对路径 |
| `source_sheet` | `str` | 是 | 当前固定为 `服务导师` |
| `source_row` | `int` | 是 | Excel 实际行号 |
| `original_fields` | `OriginalFields` | 是 | 九个原始字段完整值 |

`OriginalFields` 包含：

- `序号: int | str | null`
- `导师姓名: str | null`
- `性别: str | null`
- `城市: str | null`
- `职业年限: int | str | null`
- `可辅导学员职级: str | null`
- `行业标签: str | null`
- `从业经历: str | null`
- `背景经验: str | null`

original_fields 必须保留 Excel 读取到的原始值。用于分隔、映射和清洗的副本不得覆盖 original_fields。

### 4.4 MentorExtraction

#### 4.4.1 industry_tags

每项包含：

| 字段 | 类型 | V1 要求 |
|---|---|---|
| `raw_industry` | `str` | 必填 |
| `normalized_industry` | `str | null` | 字段必须存在 |
| `industry_category` | `str | null` | soft taxonomy，不做硬枚举校验 |
| `mapping_status` | `MappingStatus` | 必填 |
| `industry_derivation` | `str | null` | 可选 |
| `evidence` | `list[Evidence]` | 至少一条 |
| `confidence` | `Confidence` | 必填 |

抽取优先级：

1. 优先使用原 Excel 的“行业标签”；
2. 原字段不足时，从“从业经历”和“背景经验”中的明确行业表述补充；
3. 只有本地存在已确认的公司—行业映射时，才允许根据组织名称补充行业；
4. 不允许模型临时依赖世界知识，把任意公司强行映射到行业。

soft taxonomy 只提供推荐分类，不限制输出。遇到分类表以外的真实行业时：

- 保留 raw_industry；
- 不硬塞到相近行业；
- mapping_status 使用 `unmapped`；
- industry_category 可以使用 `other` 或 `null`；
- normalized_industry 可以保留轻度清洗后的 raw，也可以为 `null`。

存在多个合理分类时使用 `ambiguous`，不得静默选择其中一个。

#### 4.4.2 career_experiences

每项包含：

| 字段 | 类型 | V1 要求 |
|---|---|---|
| `raw_name` | `str` | 必填 |
| `normalized_name` | `str | null` | 字段必须存在 |
| `mapping_status` | `MappingStatus` | 必填 |
| `relationship` | `OrganizationRelationship` | 必填 |
| `raw_title` | `str | null` | 可选 |
| `normalized_title` | `str | null` | 可选 |
| `title_mapping_status` | `MappingStatus | null` | 可选 |
| `employment_status` | `EmploymentStatus` | 必填 |
| `time_period_raw` | `str | null` | 可选 |
| `context_raw` | `str | null` | 可选 |
| `evidence` | `list[Evidence]` | 至少一条 |
| `confidence` | `Confidence` | 必填 |

公司归一规则：

- 模型负责抽取 raw_name 和关系；
- normalized_name 优先由程序中的安全别名表生成；
- 只做常见简称、品牌名和已确认别名归一；
- 不生成工商全称；
- 无安全映射时保留 raw_name，mapping_status 为 `unmapped`；
- 多个公司可能匹配时 normalized_name 为 `null`，mapping_status 为 `ambiguous`。

关系规则：

- “历任、曾任、任职、就职、曾在、加入、担任某公司某岗位”可以支持 employer；
- “服务于”如果不能证明劳动关系，不得标为 employer；
- “客户包括、为某公司提供服务”标为 client；
- “参与某项目、交付某项目”标为 project；
- “合作伙伴、联合开展”标为 partner；
- 只有组织名称、没有关系语句时标为 unknown。

后续业务查询“曾就职公司”时，只筛选 relationship 为 employer 的项。

#### 4.4.3 skills

每项包含：

| 字段 | 类型 | V1 要求 |
|---|---|---|
| `raw_skill` | `str` | 必填 |
| `normalized_skill` | `str | null` | 字段必须存在 |
| `skill_category` | `SkillCategory | null` | 可选 |
| `mapping_status` | `MappingStatus` | 必填 |
| `evidence` | `list[Evidence]` | 至少一条 |
| `confidence` | `Confidence` | 必填 |

技能规则：

- raw_skill 允许自由抽取；
- normalized_skill 只进行轻度同义归一，例如“简历修改”和“简历优化”可归并；
- 不将宽泛表达扩张为更强能力；
- 不根据职位名称自动推导技能；
- 没有明确技能证据时不输出；
- 无安全归一时保留 raw_skill，mapping_status 为 unmapped。

#### 4.4.4 credentials_and_awards

每项包含：

| 字段 | 类型 | V1 要求 |
|---|---|---|
| `raw_name` | `str` | 必填 |
| `normalized_name` | `str | null` | 字段必须存在 |
| `mapping_status` | `MappingStatus` | 必填 |
| `category` | `CredentialCategory` | 必填 |
| `issuer_raw` | `str | null` | 可选 |
| `issuer_normalized` | `str | null` | 可选 |
| `issuer_mapping_status` | `MappingStatus | null` | 可选 |
| `credential_status` | `CredentialStatus` | 必填 |
| `evidence` | `list[Evidence]` | 至少一条 |
| `confidence` | `Confidence` | 必填 |

证书与奖项规则：

- 证书、资质、认证和奖项均收录，但必须分类；
- “持有、获得、通过、获评、荣获”可支持明确归属；
- “准 PCC”应标为 candidate，不能标为 held；
- “参加培训”不等于取得证书；
- “搭建认证体系”不等于导师本人持证；
- 普通讲师、导师、顾问身份不能包装成资格证。

#### 4.4.5 education

每项包含：

- `institution_raw: str`
- `institution_normalized: str | null`
- `institution_mapping_status: MappingStatus`
- `degree_raw: str | null`
- `degree_normalized: str | null`
- `degree_mapping_status: MappingStatus | null`
- `major_raw: str | null`
- `major_normalized: str | null`
- `major_mapping_status: MappingStatus | null`
- `education_type: degree / executive_education / non_degree / unknown | null`
- `evidence: list[Evidence]`
- `confidence: Confidence`

只出现学校时，不推测学历、专业或毕业状态。

#### 4.4.6 target_mentees

每项包含：

- `raw_audience: str`
- `normalized_audience: str | null`
- `mapping_status: MappingStatus`
- `dimension: career_stage / seniority / industry / job_function / special_group / other | null`
- `evidence: list[Evidence]`
- `confidence: Confidence`

优先使用“可辅导学员职级”，长文本只作为补充证据。

#### 4.4.7 career_highlights

每项包含：

- `type: str | null`
- `statement: str`
- `metrics: list[Metric] | null`
- `evidence: list[Evidence]`
- `confidence: Confidence`

Metric 可以包含：

- `name`
- `value`
- `unit`
- `qualifier`

V1 不强制 metrics 完整解析。数字、比例、人数一旦输出，必须能在 evidence 中找到对应原文。

#### 4.4.8 summary

summary 整体允许为 `null`。存在时包含：

- `value: str`
- `evidence: list[Evidence]`
- `confidence: Confidence`

建议限制为 50–100 个中文字符，只总结已有抽取结果，不增加宣传性结论。

### 4.5 QualityIssue

每项包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | `str` | 稳定的问题代码 |
| `severity` | `warning / error` | 严重程度 |
| `path` | `str | null` | 对应结果路径，例如 `skills[2]` |
| `source_field` | `str | null` | 涉及的原字段 |
| `message` | `str` | 不含密钥和完整敏感原文的说明 |

V1 建议问题代码：

- `empty_source_row`
- `missing_required_source_field`
- `duplicate_mentor_id`
- `suspected_column_shift`
- `unmapped_industry`
- `ambiguous_mapping`
- `loose_evidence_match`
- `invalid_evidence`
- `extracted_item_dropped`
- `model_schema_validation_failed`
- `model_request_failed`

### 4.6 MentorResult

最终 JSONL 每行是一个 MentorResult：

| 字段 | 类型 | 来源 |
|---|---|---|
| `schema_version` | `str` | 程序 |
| `prompt_version` | `str` | 程序 |
| `industry_taxonomy_version` | `str` | 程序 |
| `mentor_id` | `str` | MentorInput |
| `record_hash` | `str` | MentorInput |
| `source` | `object` | MentorInput |
| `original_fields` | `OriginalFields` | MentorInput |
| `normalized_profile` | `object` | 程序和抽取结果 |
| `industry_tags` | `list` | MentorExtraction |
| `career_experiences` | `list` | MentorExtraction |
| `skills` | `list` | MentorExtraction |
| `credentials_and_awards` | `list` | MentorExtraction |
| `education` | `list` | MentorExtraction |
| `target_mentees` | `list` | MentorExtraction |
| `career_highlights` | `list` | MentorExtraction |
| `summary` | `object | null` | MentorExtraction |
| `quality_issues` | `list[QualityIssue]` | 程序 |
| `processing` | `ProcessingMetadata` | 程序 |

ProcessingMetadata 包含：

- `status: success`
- `attempt_count: int`
- `processed_at: datetime`
- `model_service_name: str`
- `model_name: str | null`
- `latency_ms: int | null`

不得保存 AccessKey、API Key、Authorization 请求头或 `.env` 内容。

所有列表字段缺失时返回 `[]`，单值缺失时返回 `null`。禁止使用“未知”“暂无”“无”等字符串作为空值占位符。

## 5. Soft Industry Taxonomy V1

以下 30 类只作为推荐映射目标，不作为 Pydantic 硬枚举：

1. 互联网与平台经济
2. 软件与信息技术
3. 人工智能、大数据与云计算
4. 半导体、电子与通信
5. 银行、证券、基金与金融科技
6. 保险
7. 汽车与智能出行
8. 新能源与电力
9. 工业制造、机械与自动化
10. 化工与新材料
11. 医药与生物科技
12. 医疗与健康服务
13. 快速消费品与食品饮料
14. 零售与电子商务
15. 奢侈品、时尚与体育用品
16. 房地产
17. 建筑与工程
18. 家居与建材
19. 物流与供应链
20. 教育与培训
21. 咨询与专业服务
22. 人力资源服务与猎头
23. 法律、财税与审计
24. 媒体、广告与公共关系
25. 文化、娱乐与游戏
26. 酒店、餐饮与旅游
27. 交通运输与航空
28. 能源、矿业与资源
29. 政府、公共事业与社会组织
30. 其他

映射注意事项：

- `IT` 可以安全映射到“软件与信息技术”；
- `互联网` 可以安全映射到“互联网与平台经济”；
- `科技` 不能脱离上下文自动归入软件、AI 或电子；
- `新能源智能` 需要根据上下文判断汽车、电力或其他行业；
- `国央企、外企、世界 500 强、大厂、创业公司`是企业属性，不是行业；
- `跨行业`应拆成多个行业项，不设为单独行业；
- soft taxonomy 外的真实行业保留 raw，不强制映射到“其他”。

## 6. Evidence 两级校验

### 6.1 严格匹配

在 evidence 声明的同一个 source_field 中执行：

```text
quote in original_fields[source_field]
```

成功时：

- `match_type = strict`；
- 不产生质量告警。

### 6.2 宽松匹配

严格匹配失败后，对 quote 和目标原字段执行相同的规范化，再进行包含匹配：

1. Unicode NFKC 规范化；
2. 英文字母转为统一大小写；
3. 删除空格、制表符和换行；
4. 删除有限集合的中英文分隔标点，例如逗号、句号、顿号、分号、冒号、括号、引号、竖线和连接号；
5. 不改变汉字、字母、数字的顺序；
6. 不做同义词替换；
7. 不允许跨 source_field 拼接匹配。

为降低误匹配风险，宽松匹配后的 quote 建议至少包含 4 个有效字符；更短证据原则上要求严格匹配。

宽松匹配成功时：

- 保留抽取项；
- `match_type = loose`；
- 增加 `loose_evidence_match` warning；
- warning 指明对应结果 path 和 source_field。

### 6.3 完全失败

严格和宽松匹配都失败时：

- `match_type = invalid`；
- 对应抽取项不得作为正常可信结果保留；
- 默认从成功结果数组中删除该项；
- 增加 `invalid_evidence` 和 `extracted_item_dropped` quality issue；
- 质量问题中只保存必要的类型、路径和简短说明，不把疑似幻觉当作事实回写。

如果模型根对象不是合法 JSON、核心字段校验失败，或大量条目 evidence 无效，则进行有限重试。重试后仍失败时，整行写入 `failed_rows.jsonl`。

某个非核心抽取项被删除不必导致整位导师失败；只要 MentorResult 根结构合法并保留了可验证结果，该导师仍可成功，同时携带 warning。

## 7. 单导师输入和 HTTP 协议

### 7.1 保持 OpenAI-compatible 请求格式

不得把 MentorInput 增加到 HTTP body 顶层。现有请求结构保持不变：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "这里是序列化后的 MentorInput JSON 字符串"
    }
  ],
  "stream": false
}
```

接口继续使用：

```text
POST /openai/v1/chat/completions
```

V1 的 batch 请求使用一条 user message，message.content 是单个 MentorInput 的 JSON 字符串。main.py 从消息中解析 MentorInput，不改变 AgentRunServer 的顶层协议模型。

响应仍保持 OpenAI-compatible 结构。最终 MentorResult JSON 作为：

```text
choices[0].message.content
```

中的字符串返回。客户端取得 content 后再解析一次 JSON。

### 7.2 行转 message.content 规则

推荐 message.content 只包含 MentorInput JSON，不把导师数据重写成自然语言简历：

1. 九个原字段按 Excel 固定顺序写入 original_fields；
2. 使用 UTF-8 和 `ensure_ascii=False` 序列化；
3. 空值使用 JSON `null`；
4. 从业经历和背景经验保留原始换行；
5. 行业标签和职级字段保留原始分隔符；
6. 不在调用模型前覆盖或改写 original_fields；
7. 不截断当前导师文本；
8. 一次请求只包含一个导师；
9. batch 固定使用 `stream=false`；
10. 不在控制台或日志中打印完整 message.content。

V1 不移除 OpenAI-compatible 的 stream 字段，但结构化抽取的正确性和批处理恢复只对 `stream=false` 路径提供保证。

## 8. 增量处理与输出

### 8.1 mentor_id 和 record_hash

V1 推荐：

- `mentor_id = service_mentor:{序号}`；
- 导师姓名不进入 ID，避免姓名修订导致身份变化；
- 序号缺失或重复时，不调用模型，直接写入失败记录；
- `record_hash` 由九个原始字段的规范 JSON 计算 SHA-256。

跳过条件必须同时满足：

```text
mentor_id 已成功处理 AND record_hash 与当前行一致
```

同一 mentor_id 的 record_hash 发生变化时必须重新处理，不能因为旧版本成功而跳过。

### 8.2 Checkpoint

建议目录：

```text
outputs/
  checkpoints/
    success_rows.jsonl
  mentor_results.jsonl
  failed_rows.jsonl
  mentor_review.xlsx
```

处理规则：

- 每条成功结果立即追加到 success checkpoint，并刷新文件缓冲；
- 每条最终失败立即追加到 failed_rows.jsonl；
- failed_rows.jsonl 可以保留失败历史；
- 失败记录后续成功时，以最新成功状态为准；
- 整批结束后，根据当前 Excel 的 mentor_id 和 record_hash 生成去重后的 mentor_results.jsonl；
- 同一 ID 的旧 hash 结果不进入当前最终文件；
- 如果当前版本处理失败，旧版本成功结果不得伪装成当前有效结果。

failed_rows.jsonl 建议包含：

- mentor_id；
- record_hash；
- source_file、source_sheet、source_row；
- original_fields；
- error_type；
- sanitized_error_message；
- attempt_count；
- failed_at；
- retriable。

AccessKey、API Key、请求头和环境变量值不能进入失败文件。

### 8.3 新 Excel

不覆盖原始 Excel。建议生成以下 Sheet：

- `导师总览`
- `行业标签`
- `任职经历`
- `技能`
- `证书资质奖项`
- `教育背景`
- `辅导人群`
- `职业亮点`
- `质量问题`
- `处理失败`

所有明细 Sheet 至少包含：

- mentor_id；
- 导师姓名；
- raw 字段；
- normalized 字段；
- mapping_status；
- evidence_source_field；
- evidence_quote；
- evidence_match_type；
- confidence。

## 9. 文件职责

### 9.1 main.py

main.py 保持薄入口：

- 加载 `.env` 中的模型配置；
- 创建导师抽取 Agent；
- 保留 AgentRunServer 和 `/openai/v1/chat/completions`；
- 从最后一条 user message.content 解析 MentorInput；
- 调用单导师提取服务；
- 将 MentorResult 序列化为 JSON 字符串；
- 保持 OpenAI-compatible 请求和响应格式；
- 不读取 Excel；
- 不执行批处理；
- 不启用沙箱；
- 不打印原始事件和导师全文；
- 后续增加 `if __name__ == "__main__"` 启动保护。

### 9.2 mentor_agent/prompts.py

集中维护：

- `PROMPT_VERSION`；
- 系统 Prompt；
- soft industry taxonomy；
- confidence 规则；
- mapping_status 规则；
- 组织关系判定规则；
- 证书与奖项判定规则；
- evidence 输出要求；
- 正反例。

必须包含的反例：

- “服务某公司项目”不是 employer；
- “客户包括某公司”不是 employer；
- “搭建认证体系”不是本人证书；
- “准 PCC”不是已持有 PCC；
- “担任某公司 HRBP”可以是 employer；
- “国央企、外企、500 强”不是行业；
- 不能从职位名称自动推导技能。

### 9.3 mentor_agent/schemas.py

- 定义 MentorInput、MentorExtraction、MentorResult；
- 定义 Confidence、MappingStatus、Relationship 等枚举；
- V1 只强校验核心字段；
- 所有模型设置 `extra="forbid"`；
- 空数组和 null 使用稳定默认值。

### 9.4 mentor_agent/extractor.py

- 单导师模型调用；
- Pydantic 解析；
- 有限重试；
- evidence 两级校验；
- 无效抽取项剔除；
- 质量问题组装；
- 不负责 Excel 和 HTTP 服务启动。

### 9.5 mentor_agent/normalizers.py

- 公司安全别名映射；
- 技能轻度同义归一；
- soft industry taxonomy 映射；
- mapping_status 计算；
- 确定性去重；
- 不调用模型，不使用未确认的外部公司知识。

### 9.6 mentor_agent/excel_io.py

- 读取 `服务导师` Sheet；
- 校验九列字段；
- 保留 original_fields；
- 跳过空行；
- 识别字段缺失和疑似错位；
- 生成新的多 Sheet Excel；
- 不覆盖原文件。

### 9.7 test_request.py

- 使用合成导师数据调用本地接口；
- 保持现有 OpenAI-compatible body；
- 固定 `stream=false`；
- 从 `choices[0].message.content` 解析 MentorResult；
- 执行 Pydantic 校验；
- 验证 client 不会变成 employer；
- 验证认证体系不会变成个人证书；
- 验证 evidence 严格和宽松匹配；
- 不使用真实密钥或完整真实导师样本。

### 9.8 batch_extract.py

- 逐行读取 Excel；
- 构造 MentorInput；
- 计算 mentor_id 和 record_hash；
- 加载成功 checkpoint；
- 跳过未变化的成功记录；
- 调用本地 `/openai/v1/chat/completions`；
- 执行超时和有限重试；
- 成功写 checkpoint；
- 失败写 failed_rows.jsonl；
- 生成最终去重 JSONL；
- 生成新的人工审阅 Excel；
- 不包含 Prompt 和抽取业务规则。

## 10. 隐私与安全

- 只调用当前 `.env` 配置的、已授权的 AgentRun 模型服务；
- 不将 `.env`、AccessKey、API Key、Authorization 头写入日志或输出；
- 日志默认只记录 mentor_id、source_row、状态、耗时和错误类型；
- 不在普通 info 日志中记录导师全文或完整模型响应；
- 原始导师 Excel、JSONL、审阅 Excel 和失败文件不进入 Git；
- 不启用沙箱和任意代码执行；
- 本地批处理只连接 `127.0.0.1:9000`。

## 11. 阶段式开发计划

### 阶段 0：源码安全基线

目标：建立不包含密钥、私人数据和构建产物的 Git 基线。

任务：

- 创建 `.gitignore`；
- 排除：
  - `.env`
  - `python/`
  - `outputs/`
  - `logs/`
  - `__pycache__/`
  - `*.pyc`、`*.pyo`、`*.pyd`
  - `.pytest_cache/`
  - 临时文件和 `~$*.xlsx`
  - 原始导师 Excel
- 检查待提交文件中没有密钥和个人数据；
- 在干净环境中仅根据 requirements.txt 重建依赖；
- 验证 `python main.py` 可以启动；
- 验证 OpenAI-compatible 测试请求；
- 如果 requirements.txt 声明版本和实际模板版本不一致，先明确并锁定；
- 初始化 Git；
- 提交当前可运行模板基线。

`python/` 当前作为约 183 MB 的 vendored 依赖目录，不进入普通源码 Git。如果 AgentRun 后续部署要求携带该目录，则在构建或发布阶段生成，并作为部署产物管理。

完成标准：

- Git 基线中无密钥、原始导师资料和输出文件；
- 仅凭受控依赖定义可以重建本地服务；
- 基线 commit 可运行。

### 阶段 1：数据契约与测试样本

目标：冻结 V1 Schema 和抽取口径。

任务：

- 实现公共枚举和三个数据层 Schema；
- 固定 prompt_version 和 taxonomy_version；
- 建立 soft industry taxonomy；
- 建立公司关系、证书、技能的正反例；
- 创建匿名合成测试样本；
- 测试 JSON、confidence、mapping_status、relationship 和 raw/normalized 核心约束。

完成标准：

- 合法样本通过 Pydantic；
- 非法 confidence、relationship、mapping_status 和额外字段被拒绝；
- optional 复杂字段缺失不会导致失败。

### 阶段 2：Excel 与确定性预处理

目标：可靠地将 Excel 单行转换成 MentorInput。

任务：

- 使用只读模式读取 Excel；
- 校验 Sheet 和九列字段；
- 过滤两条仅有序号的空记录；
- 检测缺失字段和疑似字段错位；
- 生成 mentor_id；
- 规范序列化并计算 record_hash；
- 保证 original_fields 不被覆盖；
- 编写 Excel 解析单元测试。

完成标准：

- 识别 121 条实际导师记录；
- 空记录不调用模型；
- 同一行重复读取产生相同 hash；
- 原始字段完整可回溯。

### 阶段 3：单导师结构化抽取

目标：得到有证据、可验证的 MentorExtraction。

任务：

- 编写专用系统 Prompt；
- 接入 structured output；
- 实现严格组织关系规则；
- 实现行业、技能、公司和资质的 raw/normalized/mapping_status；
- 实现证书状态与奖项分类；
- 实现 evidence 严格和宽松校验；
- 删除完全无效证据的抽取项；
- 实现有限重试和质量告警。

完成标准：

- 输出是合法 MentorExtraction；
- client/project/partner 不会被默认标成 employer；
- 普通经历不会被包装成证书；
- 无法标准化的结果仍保留 raw；
- evidence 完全失败的项目不作为可信结果输出。

### 阶段 4：OpenAI-compatible 本地接口

目标：在不破坏现有协议的情况下提供单导师识别。

任务：

- 保持 `/openai/v1/chat/completions`；
- 保持 messages 和 stream 顶层格式；
- 从 message.content 解析 MentorInput；
- 调用 extractor；
- 将 MentorResult 作为 message.content JSON 字符串返回；
- 更新 test_request.py；
- 验证正常、错误输入和模型失败路径；
- 确认日志不泄露导师全文和密钥。

完成标准：

- 现有 OpenAI-compatible 客户端仍能请求接口；
- batch 使用 `stream=false` 可稳定得到 MentorResult；
- 非法 MentorInput 明确失败，不返回伪造结果。

### 阶段 5：批处理、断点续跑和导出

目标：可靠处理完整 Excel，并提供程序和人工两类输出。

任务：

- 实现 batch_extract.py；
- 逐条调用本地 Agent；
- 成功后立即写 checkpoint；
- 失败写 failed_rows.jsonl；
- 使用 mentor_id + record_hash 判断跳过或重跑；
- 生成当前版本去重后的 mentor_results.jsonl；
- 生成多 Sheet mentor_review.xlsx；
- 验证重新运行不会重复调用未变化成功记录；
- 验证失败记录可以重试并转为成功。

完成标准：

- 中断后可以继续；
- 未变化成功记录被跳过；
- 内容变化记录被重新处理；
- 原始 Excel 不被修改；
- JSONL 与 Excel 结果可相互追溯。

### 阶段 6：质量评估与全量运行

目标：在人审确认后处理全部导师。

任务：

- 先处理 10 条覆盖典型边界的样本；
- 人工审查 employer/client/project/partner；
- 人工审查证书、奖项、教育和技能；
- 人工审查 loose evidence warnings；
- 调整 Prompt、soft taxonomy 和安全别名表；
- 扩展到 20–30 条抽样；
- 达到验收标准后处理全部 121 条；
- 汇总失败项、unmapped 项、ambiguous 项和低置信度项。

完成标准：

- 所有成功项 JSON 合法；
- 所有保留的语义抽取项 evidence 至少通过严格或宽松匹配；
- 完全无效 evidence 不进入可信结果；
- 曾就职公司只来自 employer；
- 标准化失败不丢失 raw；
- 全量失败和警告均可审计。

## 12. V1 明确不做

- 不接 MySQL 或 PostgreSQL；
- 不做网页上传；
- 不启用沙箱；
- 不做 RAG 或向量检索；
- 不调用外部工商公司库；
- 不补全公司工商全称；
- 不建立硬行业枚举；
- 不建立硬技能词表；
- 不自动把普通经历提升为证书、奖项或技能；
- 不覆盖原始导师 Excel；
- 不把私有数据和生成结果提交到 Git。

