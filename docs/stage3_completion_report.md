# 阶段 3 完成报告：单导师结构化抽取

## 1. 阶段结论

阶段 3 已完成。项目现在具备一个不读取 Excel、不写 outputs、可注入模型客户端的单导师抽取管线：接收 `MentorInput`，构造 JSON-only prompt，有限重试模型调用，解析并校验 `MentorExtraction`，执行 evidence 校验和确定性轻量归一，最后组装通过 Pydantic 校验的 `MentorResult`。

本阶段没有调用真实 AgentRun 模型，没有访问 `/openai/v1/chat/completions`，没有实现全量批处理，也没有修改 `main.py`。所有模型相关测试都使用离线 fake response。

## 2. 实现文件

### 新增

- `mentor_agent/extractor.py`
  - 单导师 prompt/messages 构造；
  - callable 或 `.invoke(messages)` 模型客户端注入；
  - JSON 解析和 `MentorExtraction` 校验；
  - 最多指定次数的有限重试；
  - evidence 过滤、确定性归一和关系/证书 guardrail；
  - `MentorResult` 和 processing metadata 组装；
  - 公开 `extract_mentor_with_model` 和 `extract_single_mentor`。

- `mentor_agent/evidence.py`
  - strict、loose、invalid evidence 分类；
  - 程序覆盖模型提供的 `match_type`；
  - 严格限制在 evidence 声明的 `source_field` 内匹配。

- `mentor_agent/normalizers.py`
  - 公司、技能、行业的轻量别名归一；
  - ambiguous/unmapped 明确返回；
  - 稳定保序去重。

- `tests/test_evidence.py`
- `tests/test_normalizers.py`
- `tests/test_extractor.py`
  - 全部使用匿名合成数据和 fake model，不依赖网络或本地 AgentRun 服务。

- `docs/stage3_completion_report.md`

### 修改

- `mentor_agent/prompts.py`
  - prompt 版本升级为 `mentor-extraction-v1.1`；
  - 新增 Stage 3 JSON-only 系统 prompt；
  - 固化关系、行业、技能、证书和 evidence 约束。

- `tests/test_schemas.py`
  - 更新 prompt 版本断言。

### 未修改

- `main.py`
- `requirements.txt`
- Excel 读取和阶段 2 逻辑
- `test_request.py`

## 3. 单导师抽取流程

```text
MentorInput
  -> build_extraction_messages
  -> 注入的 model_client.invoke(messages) 或 callable(messages)
  -> JSON 解析
  -> MentorExtraction Pydantic 校验
  -> evidence strict/loose/invalid 校验
  -> 删除无有效 evidence 的抽取项
  -> 公司/技能/行业轻量归一和去重
  -> 组织关系与证书语义 guardrail
  -> MentorResult Pydantic 组装
```

模型根对象不是合法 JSON、返回类型不支持、模型请求抛错或 `MentorExtraction` 核心结构校验失败时，会在 `max_attempts` 范围内重试。默认两次。全部失败后抛出 `ExtractionError`，不返回 dummy 数据，也不静默吞错。

evidence 或非核心抽取项失败不会导致整位导师失败。

## 4. Prompt

当前版本：

```text
mentor-extraction-v1.1
```

系统 prompt 明确要求：

- 只输出一个合法 JSON 对象；
- 不输出 Markdown、代码块或推理说明；
- 不编造；
- 每个抽取项提供 evidence；
- confidence、relationship、mapping_status 只能使用 Schema 允许值；
- 行业 taxonomy 是 soft taxonomy；
- 技能允许自由抽取；
- 服务、客户、合作关系不能当成 employer；
- 搭建认证体系不代表本人持证；
- 准 PCC 不能标为 held；
- `match_type` 由程序计算。

最后一条 user message 的 content 是 JSON 字符串，包含完整 `mentor_input` 和 `MentorExtraction` output schema，便于阶段 4 接入现有 messages 协议。

## 5. Evidence 校验

### Strict

```text
quote in original_fields[source_field]
```

成功后写入 `match_type=strict`，不产生 warning。

### Loose

只执行以下有限归一：

1. Unicode NFKC；
2. `casefold` 统一大小写；
3. 删除空格、制表符、换行等 whitespace；
4. 删除代码中明确列出的有限中英文标点。

不做同义词替换，不跨 `source_field`。成功后写入 `match_type=loose`，并增加 `loose_evidence_match` warning。

### Invalid

strict 和 loose 都失败时：

- 写入程序判定的 invalid 状态；
- 将该 evidence 从抽取项移除；
- 增加 `invalid_evidence` warning；
- 如果抽取项没有剩余有效 evidence，则删除整个抽取项并增加 `extracted_item_dropped` warning。

summary 采用相同规则；无有效 evidence 时设置为 `None`。

## 6. 轻量归一和语义 guardrail

### 公司

- 仅使用代码内少量明确别名；
- 不补工商全称；
- 无安全映射时 normalized 保留 raw，状态为 `unmapped`；
- 多候选别名返回 normalized `None` 和 `ambiguous`。

### 行业

- taxonomy 内精确值或安全别名可以 `mapped`；
- taxonomy 外行业保留 raw，状态为 `unmapped`；
- “科技”等多候选宽泛词返回 `ambiguous`；
- 不硬塞到“其他”或近似行业。

### 技能

- 允许任意 `raw_skill`；
- 只处理少量安全同义词；
- 未命中时保留 raw 并标记 `unmapped`；
- 不根据职位推导技能。

### 关系和证书

- 模型把组织标为 employer 但 evidence 不含明确任职语义时，程序会按项目、服务、合作语境纠正为 project、client、partner 或 unknown，并记录 warning；
- “搭建/建设认证体系”且没有本人持有/获得语义时，证书项会被删除；
- “准 PCC/准认证”误标 held 时会纠正为 candidate。

## 7. 测试

用户执行命令：

```powershell
conda activate tutor
python -m pytest -q
```

本次在同一 `tutor` 环境中的结果：

```text
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 1.02s
```

测试覆盖：

- strict/loose/invalid evidence；
- loose warning 和 invalid item 删除；
- evidence 不跨字段匹配；
- 非法 JSON 重试及最终显式失败；
- 非法 confidence 被 Pydantic 拒绝；
- client/project 不会保留为 employer；
- 明确任职仍为 employer；
- 搭建认证体系不变成本人证书；
- 准 PCC 不保留为 held；
- taxonomy 外行业保留 raw/unmapped；
- 自由技能和未知公司保留 raw/unmapped；
- ambiguous 公司映射；
- 稳定去重；
- 模型输出和 `MentorResult` 都不能通过额外字段保存 AccessKey、API Key、Authorization 或 `.env`。

`git diff --check` 通过，仅有 Git 的 CRLF 转换提示。

## 8. 真实模型与 smoke test

本阶段没有调用真实模型，也没有新增真实接口 smoke script。原因是阶段 3 的完成标准可以由可注入 fake model 完整离线验证，而 `docs/mentor_extraction_plan.md` 已将 OpenAI-compatible 本地接口接入划分到阶段 4。

因此没有依赖 `.env`、本地服务启动状态或外部网络，也没有打印密钥或真实导师资料。

## 9. 当前限制

- 公司、行业和技能别名表刻意保持很小，只覆盖明确安全映射；
- loose evidence 不理解同义词和语义等价；
- 关系纠正使用有限中文触发词，不替代模型对复杂句法的完整理解；
- 当前只支持同步 callable/`.invoke()` 客户端；
- 没有直接接入 `main.py`、HTTP 服务或流式返回；
- 没有批处理、checkpoint 或 outputs 写入。

## 10. 下一阶段建议

阶段 4 可在不改变现有 `/openai/v1/chat/completions`、messages 顶层结构和 `stream=false` 返回形式的前提下：

1. 从最后一条 user message content 解析 `MentorInput`；
2. 用现有 AgentRun/LangChain client 调用 `extract_single_mentor`；
3. 将 `MentorResult.model_dump_json()` 放回 `choices[0].message.content`；
4. 增加本地接口正常输入、错误输入和模型失败测试；
5. 保持真实服务失败显式，不加入静默 mock fallback。
