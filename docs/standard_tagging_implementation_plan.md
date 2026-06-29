# 标准标签能力实施计划

## 实施状态

- Phase 1：已完成。
- Phase 2：已完成。

## 总体约束

- 只接入 simple 模式，不修改 full 模式。
- 标准标签默认关闭；开启后以 `configs/职位类型_2.txt` 为唯一 taxonomy 真源。
- 上半部分非 `-` 行仅为职位分组，`-` 后内容为标准职位标签，最后一条职位之后的独立行是标准行业标签。
- 行业标签与职位标签始终分开；canonical 标准标签只能来自候选池。
- 保留旧 simple 字段与旧 JSONL 解析能力。

## Phase 1：标准标签入库闭环

### 修改文件

- `configs/职位类型_2.txt`
- 新增 `mentor_agent/tag_taxonomy.py`
- `mentor_agent/simple_schemas.py`
- `mentor_agent/simple_prompts.py`
- `mentor_agent/simple_extractor.py`
- `main.py`
- `batch_extract.py`
- Phase 1 对应测试

### 核心逻辑

#### Taxonomy

新增不可变 `TagTaxonomy`，保存：

- `position_groups`
- `position_tags`
- `industry_tags`
- `source_path`
- `taxonomy_hash`

解析规则：

1. 使用 `utf-8-sig` 读取，忽略 BOM、换行风格、首尾空白和尾部空行。
2. `-` 开头的非空行是职位标签。
3. 最后一条职位之前，非空且不以 `-` 开头的行是职位分组。
4. 最后一条职位之后，所有非空独立行是行业标签。
5. 职位标签按首次出现顺序去重；同一标签可以保留在多个分组映射中。
6. 分组标题绝不进入 `position_tags`，标准标签不做模糊改写。

解析器必须 fail fast，不静默猜测或修正：

- 没有职位标签；
- 没有行业标签；
- 职位标签之前没有分组；
- 行业区出现 `-` 项；
- 空标签或无法确定所属分组；
- 文件不存在、编码或结构错误。

`taxonomy_hash` 不使用原始文件字节。它基于解析后的 canonical taxonomy 结构计算：将 `position_groups`、`position_tags`、`industry_tags` 以固定字段顺序、稳定列表顺序和固定 JSON 分隔符序列化，再对 UTF-8 JSON 计算 SHA-256。BOM、CRLF/LF 和尾部空行变化不得改变 hash。

#### Schema

新增：

- `TaggedIndustry`
- `TaggedPosition`
- `TaggedCompany`
- `PositionRelationType`

`PositionRelationType` 仅允许：

- `firsthand_role`
- `managed_team`
- `recruited_or_evaluated`
- `related`

`SimpleMentorExtraction` 增加：

- `industry_tags`
- `position_tags`
- `company_tags`
- `raw_keywords`
- `review_required`
- `review_reasons`

所有新集合字段提供空默认值。保留 `industries/companies/roles/skills/keywords/...` 等旧字段。

`SimpleMentorResult.prompt_version` 支持：

- `mentor-simple-v1`
- `mentor-simple-tagged-v1`

`SimpleMentorResult` 根级增加：

- `standard_tags_enabled: bool = False`
- `taxonomy_hash: str | None = None`

这两个字段属于 result-level metadata，不放入 extraction。

#### Prompt

- 完整保留旧 simple 单条和 batch prompt。
- 新增 tagged 单条和 batch prompt。
- payload 根级传入 `industry_tag_candidates` 和 `position_tag_candidates`；batch 候选池只传一次。
- LLM 只能逐字选择候选池标准标签，不输出职位分组，不把职位自动推导为行业。
- evidence 必须是导师允许字段中的原文片段。
- relation type 只能使用四个枚举；HR 招聘算法岗应为 `recruited_or_evaluated`。
- `review_required/review_reasons` 不要求模型生成。

#### Canonical sanitize

simple 单条和 batch extractor 增加可选 `taxonomy` 参数：

- `taxonomy is None`：继续走旧 prompt 和旧处理流程。
- taxonomy 存在：走 tagged prompt，并在 Pydantic canonical 校验前进行程序化 sanitize。

`review_required/review_reasons` 必须先覆盖为程序默认值，再根据验证结果重新计算，不能信任 LLM 输出。

标准标签 evidence 默认只允许匹配以下导师原始字段：

- `行业标签`
- `从业经历`
- `背景经验`
- `可辅导学员职级`

不得使用 `导师姓名`、`性别`、`城市`、`职业年限` 作为标准标签 evidence 来源。匹配采用 NFKC、大小写、空白和常见标点规范化后，在每个允许字段内独立做子串匹配，不跨字段拼接。

处理规则：

- 池外标签移除并审核；
- evidence 为空时移除并审核；
- evidence 无法在允许原文字段中匹配时移除并审核；
- relation type 非法时移除该职位标签并审核；
- confidence 非数值或不在 0–1 时移除并审核；
- confidence `< 0.70` 时保留标签但进入审核；
- `company_tags.industry_tag` 非空时必须属于行业池；
- 标准标签重复或关系冲突时保留最高 confidence 项，冲突进入审核。

稳定审核格式：

```text
position_tags[1]|tag=人工智能|reason=evidence_empty
industry_tags[0]|tag=互联网|reason=tag_not_in_taxonomy
```

canonical 输出不能包含无 evidence 或 evidence 无法在允许原文字段中匹配的标准标签。batch 必须根据 `mentor_id` 找到对应 `MentorInput` 后逐导师验证。

#### 服务、Checkpoint 和 Review Excel

`main.py` 新增：

```env
ENABLE_STANDARD_TAGS=false
TAG_TAXONOMY_PATH=configs/职位类型_2.txt
```

- 布尔值仅接受明确的 `true/false`，非法值启动失败。
- simple + 开启时启动阶段加载一次 taxonomy；文件不存在或解析失败时 fail fast。
- simple + 关闭时不加载 taxonomy。
- full 模式不加载、不使用 taxonomy。

Checkpoint：

- 标准标签关闭时继续复用旧 simple checkpoint。
- 标准标签开启时，只复用 `standard_tags_enabled=true` 且 `taxonomy_hash` 与当前 taxonomy 一致的 checkpoint。
- 旧 checkpoint、缺少 hash 或 hash 不一致时重新抽取。
- batch 客户端期望模式与服务返回 metadata 不一致时明确失败。

Review Excel：

- 旧 simple 模式仍输出 `导师总览`、`关键词明细`、`处理失败`。
- tagged 模式新增 `标准行业标签`、`标准职位标签`、`公司标签`、`人工审核项`。
- 导师总览新增标准行业、标准职位、review 标记、review reasons 和 taxonomy hash。
- 每个 review reason 独占一行。

### 测试

- taxonomy 正确解析，分组不进入职位池。
- 无职位、无行业、职位前无分组、行业区出现 `-` 均 fail fast。
- canonical taxonomy 相同但 BOM、换行符、尾部空行不同的 hash 相同；结构变化后 hash 改变。
- 旧 simple schema、prompt、JSONL、单条和 batch 兼容。
- tagged prompt 包含候选池和关系规则。
- prompt version 同时接受旧版和 tagged 版。
- 池外标签、空 evidence、无法匹配 evidence、非法 relation type/confidence 被移除并审核。
- 只允许四个 evidence 来源字段；姓名、城市等字段中的相同文本不能通过验证。
- confidence `< 0.70` 保留但审核。
- LLM 提供的 review 字段被程序覆盖。
- batch evidence 按 mentor id 独立验证。
- checkpoint hash 不一致时不复用。
- 旧 simple 三 sheet、tagged 七 sheet 均正确。

### 风险

- 文件没有显式行业分隔标记，边界固定为“最后一条职位之后”；格式变化必须显式失败。
- tagged prompt 变长可能降低 batch 稳定性。
- taxonomy canonical 内容变化会使 tagged checkpoint 失效并重新抽取。
- evidence 只接受可验证原文片段，模型语义改写会被清理。

### 验收标准

- 开关关闭时旧 simple 主链路正常。
- 开关开启时标准标签全部来自 taxonomy。
- canonical 输出不存在非法标签、空 evidence 或无法验证的 evidence。
- 审核原因可追踪到字段、标签和原因。
- tagged 单条、batch、resume、JSONL、Excel 全链路通过。
- full 模式行为不变，完整 pytest 通过。

## Phase 2：匹配侧接入标准标签

### 修改文件

- `mentor_agent/matching/mentor_index.py`
- `mentor_agent/matching/scorer.py`
- `mentor_agent/matching/schemas.py`
- `mentor_agent/matching/formatter.py`
- `mentor_agent/matching/aliases.py`
- `configs/matching_aliases.json`
- Phase 2 对应测试和匹配文档

现有 `DEFAULT_ALIAS_PATH` 已是 `configs/matching_aliases.json`。Phase 2 在这一唯一真源上扩展，不迁移或复制 alias 文件；若未来路径变化，必须同步修改默认路径、测试和文档。

### 核心逻辑

#### Index 与召回

- `industry_tags[*].tag` 加入行业结构化文本。
- `position_tags[*].tag` 加入职位结构化文本。
- `position_tags[*].raw_keywords` 和顶层 `raw_keywords` 加入二次召回文本。
- `company_tags[*].company_name/company_type` 加入公司搜索文本。
- 旧 JSONL 缺少新字段时继续正常加载。

#### Scorer

Role match 优先级：

1. confidence `>= 0.70` 的 `position_tags.tag`；
2. 旧 `roles`；
3. 低置信度标准职位、position raw keywords、顶层 raw keywords；
4. 原文 fallback。

Industry match 优先级：

1. confidence `>= 0.70` 的 `industry_tags.tag`；
2. 旧 `industries`；
3. 低置信度标准行业和原文 fallback。

只有 confidence `>= 0.70` 的标准标签是强结构化匹配信号。低置信度标签可以展示，或作为低权重补充信号，但不能形成强命中，也不能覆盖高置信度标准标签冲突。

relation type 第一版只展示，不改变分数。本次 Phase 2 只接入 `company_tags` 搜索与展示；不实施强 `company_type` 标准化、独立公司别名库或公司权重增强，这些仅记录为后续扩展项。

#### Schema、Formatter 与 Aliases

- card/debug 增加标准行业、标准职位、raw keywords、relation type 和对应 matched signals。
- 保留旧字段，避免 formatter/reranker 大改。
- formatter 区分标准标签强命中、低置信度补充命中和 raw keyword 补充召回。
- aliases 按职位和行业 query 维度隔离：
  - AI、大模型、Agent → 职位“人工智能”；
  - 产品、PM → “产品经理”；
  - 投行 → “投融资”；
  - 基金、证券 → “证券/基金/期货”；
  - 只有明确行业意图才映射到“AI/互联网/IT”或“金融”。
- 不因“产品经理”自动增加互联网行业，不因“AI 岗位”自动扩展为 AI 行业。

### 测试

- 高置信度标准职位优先于旧 role。
- 高置信度标准行业优先于旧 industry。
- 低置信度标准标签不是强命中。
- raw keywords 只做低权重补充召回。
- relation type 不改变第一版分数。
- company tags 进入搜索和展示，但不产生新的 company type 标准化。
- aliases 按职位、行业维度隔离。
- 旧 JSONL 可加载，旧排序无非预期变化。
- formatter 能展示标准标签、confidence、relation type、来源与匹配原因。
- reranker、评估和 Top10 导出保持兼容。

### 风险

- 同一表达可能同时具有行业和职位含义，aliases 必须按字段隔离。
- 标准标签与旧字段同时命中时需避免重复计分。
- 低置信度标签或 raw keywords 权重过高会重新扩大模糊匹配范围。
- formatter 新字段可能影响现有快照和导出结构。

### 验收标准

- 高置信度标准标签成为 role/industry 首选结构化信号。
- 低置信度标签和 raw keywords 仅作补充。
- relation type 可展示但默认不影响分数。
- company tags 可搜索和展示，但没有超出范围的 company type 标准化。
- aliases 保持单一真源且不违反“职位不能自动推导行业”原则。
- 旧 JSONL、formatter、reranker 和排序评估保持兼容。
