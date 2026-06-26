# 导师抽取模型对比 Smoke Test

## 1. 测试范围与日期

- 测试日期：2026-06-24；
- 计划模型：`deepseek-v4-pro`、`qwen3.7-plus`、`deepseekv4-flash`；
- 每个模型最多处理 3 条；
- `MODEL_SERVICE_NAME`、endpoint 和凭证保持不变；
- 每次只修改 `.env` 中的 `MODEL_NAME`，并重新启动 `python main.py`；
- 批处理固定 `stream=false`，每个模型使用独立 output 目录；
- 未运行 10 条或全量。

### 数据范围说明

本次未把真实导师 Excel 内容发送到模型后端。

原因：虽然客户端请求发往 `127.0.0.1`，Stage 4 服务仍会将导师内容发送到 `.env` 指定的模型后端；当前租户安全策略无法验证该后端是否获准接收真实导师私有数据，因此阻止了真实数据调用。

为完成可执行的模型对比，改用 3 条匿名合成导师资料，覆盖：

- employer、client、project、partner、unknown；
- 明确证书、准 PCC、认证体系建设负例；
- 本科、硕士、博士教育；
- 常规技能和 taxonomy 外行业。

因此以下结论只代表匿名合成 smoke，不可直接当作真实导师三条测试结论。

## 2. 模型与输出目录

| 模型 | `.env MODEL_NAME` | 输出目录 | 状态 |
|---|---|---|---|
| DeepSeek V4 Pro | `deepseek-v4-pro` | `outputs/eval/model_eval/deepseek-v4-pro` | 3/3 成功 |
| Qwen 3.7 Plus | `qwen3.7-plus` | `outputs/eval/model_eval/qwen3.7-plus` | 3/3 成功 |
| DeepSeek V4 Flash | `deepseekv4-flash` | `outputs/eval/model_eval/deepseekv4-flash` | 0/3，HTTP 400 |

三个目录及服务器日志均位于 `.gitignore` 已排除的 `outputs/` 下。

## 3. 聚合指标

`avg_attempt_count` 同时统计成功 `MentorResult.processing.attempt_count` 和失败记录的 attempt_count。

| model_name | success | failed | avg_latency_ms | min_latency_ms | max_latency_ms | avg_attempt_count | quality_issues | invalid_evidence | loose_evidence | dropped | employer | client | project | partner | unknown | skills | credentials | education | avg_json_chars | failed error types |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| deepseek-v4-pro | 3 | 0 | 41689.0 | 36049 | 45166 | 1.0 | 0 | 0 | 0 | 0 | 2 | 2 | 1 | 1 | 1 | 10 | 3 | 3 | 4229.0 | `{}` |
| qwen3.7-plus | 3 | 0 | 73460.7 | 64573 | 86968 | 1.3 | 0 | 0 | 0 | 0 | 2 | 2 | 1 | 1 | 1 | 9 | 3 | 3 | 4136.3 | `{}` |
| deepseekv4-flash | 0 | 3 | - | - | - | 1.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | `{"http_status_error": 3}` |

## 4. 速度与成功率

### DeepSeek V4 Pro

- 成功率：100%；
- 平均延迟：41.7 秒；
- 最快：36.0 秒；
- 最慢：45.2 秒；
- 三条均在模型抽取 attempt 1 成功。

服务首次启动曾连续两次遇到 AgentRun 控制面 0.6 秒 read timeout；控制面恢复后重新启动成功，以上延迟只统计正式成功的三条请求。

### Qwen 3.7 Plus

- 成功率：100%；
- 平均延迟：73.5 秒；
- 最快：64.6 秒；
- 最慢：87.0 秒；
- 平均 attempt 1.3，说明三条中有一条在 extractor 内部发生过一次重试。

Qwen 平均延迟约为 DeepSeek V4 Pro 的 1.76 倍。DeepSeek 的平均延迟低约 43%。

### DeepSeek V4 Flash

- 本地服务可以使用该模型名启动；
- 三条请求均立即返回 HTTP 400；
- Stage 4 安全日志只记录 `mentor extraction failed`，没有返回更具体的模型后端原因；
- 按“不反复卡住”的要求，每条只请求一次，没有继续重试。

结论：`deepseekv4-flash` 在当前 `MODEL_SERVICE_NAME` 配置下不可用，可能是模型别名不受该服务支持或后端拒绝该模型配置。

## 5. Quality Issues 与 Evidence

两款成功模型均为：

- total quality issues：0；
- invalid evidence：0；
- loose evidence match：0；
- extracted item dropped：0；
- 保留 evidence 全部是 strict；
- 没有保留 invalid evidence。

在这三条合成样本上，两款模型的关系分布完全一致：

- employer：2；
- client：2；
- project：1；
- partner：1；
- unknown：1。

## 6. 轻量人工质量摘要

### Employer/client/project 是否明显误判

未发现。两款模型均正确识别：

- 明确任职为 employer；
- 提供咨询/服务为 client；
- 明确项目为 project；
- 合作为 partner；
- 仅提及组织、关系不明为 unknown。

所有 employer evidence 都包含明确任职触发词。

### 普通经历是否被当成证书

未发现。

- “认证体系建设”没有生成额外个人证书；
- 准 PCC 均被标为 candidate，而不是 held；
- 明确持有/获得的三项证书或资格均被保留；
- 两款模型的 credential_count 都是 3。

### Summary 是否明显编造

未发现明显编造。

- 两款模型都生成了 2/3 个 summary；
- 所有已生成 summary 的 evidence 都是 strict；
- summary 内容与合成输入中的年限、任职、技能、证书和教育一致；
- 两款模型各有一条没有 summary，Schema 允许 summary 为 null。

### Evidence 是否大量无法匹配

没有。两款模型均为 0 invalid、0 loose、0 dropped。

### 技能抽取是否过少或过多

- DeepSeek V4 Pro：共 10 项；
- Qwen 3.7 Plus：共 9 项。

Qwen 对三条记录均抽取 3 项技能，较克制。DeepSeek 在第二条额外把“面试官认证体系建设”抽为技能，这一项偏宽，可能属于项目/工作经历而不是导师可辅导技能。除这一项外，两者技能抽取与输入一致。

### 证书和教育是否明显漏抽

未发现。

- 两款模型均抽取 3 项证书/资格；
- 两款模型均抽取 3 项教育经历；
- 本科、工商管理硕士和机械工程博士均有结果；
- 准 PCC 状态正确。

## 7. 推荐

### 推荐主力模型

暂时推荐 `deepseek-v4-pro` 作为主力模型。

理由：

- 与 Qwen 相同的 3/3 成功率；
- 关系、证书、教育和 evidence 质量相当；
- 平均延迟低约 43%；
- 三条均在第一次 extractor attempt 成功；
- 输出 JSON 略丰富，但只多出一项偏宽技能，需要后续真实样本观察。

`qwen3.7-plus` 可作为第二候选或交叉复核模型。它的技能抽取更克制，但当前样本中速度明显较慢，并出现一次内部重试。

`deepseekv4-flash` 暂不建议进入生产候选，除非先确认当前 AgentRun 模型服务支持的准确模型标识并解决 HTTP 400。

### 是否保留 DeepSeek V4 Pro 作为疑难样本兜底

建议保留。按本次结果，它不仅适合作为疑难样本兜底，当前更适合作为主力模型。如果后续真实样本显示 Qwen 在技能精度或复杂语义上明显更优，可以将 Qwen 用于常规处理、DeepSeek V4 Pro 用于失败重试或疑难样本；但本次小样本尚不支持把 Qwen 提升为主力。

## 8. 当前环境状态

- `.env` 已从测试前备份逐字节恢复；
- 当前 `.env MODEL_NAME`：`deepseek-v4-pro`；
- `MODEL_SERVICE_NAME` 指纹与测试前一致；
- 当前没有保持运行的本地 `main.py` 服务进程；
- `.env`、备份、outputs 和 logs 均被 Git 忽略；
- 未运行真实导师 3 条、10 条或全量。

## 9. 后续建议

1. 先确认模型后端获准接收真实导师资料；
2. 在获准环境中用相同三条真实导师重跑 DeepSeek V4 Pro 和 Qwen 3.7 Plus；
3. 对 DeepSeek 的技能偏宽问题增加人工审核；
4. 查询 AgentRun 当前服务支持的 Flash 模型准确标识；
5. 真实三条结果一致后，再决定是否进行 10 条测试；
6. 不建议在真实三条完成前运行全量。
