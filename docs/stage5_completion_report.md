# 阶段 5 完成报告：批处理、断点续跑和结果导出

## 1. 阶段结论

阶段 5 已完成。项目现在具备一个同步、逐导师、可恢复的 `batch_extract.py`：复用 Stage 2 Excel 输入，固定以 `stream=false` 调用本地 OpenAI-compatible 接口，分类处理 HTTP/AgentRun/JSON/Pydantic 错误，成功即时写 checkpoint，失败即时写历史记录，最后生成当前 Excel 对应的去重 JSONL 和十个 Sheet 的审阅 Excel。

单行失败不会中断整体批处理。脚本不覆盖原始 Excel，不打印导师全文，不读取或保存密钥，也不调用本地模型接口之外的外部服务。

## 2. 修改文件

### 新增

- `batch_extract.py`
  - CLI 参数；
  - Excel 读取和有效记录切片；
  - OpenAI-compatible HTTP 请求；
  - 错误分类和有限重试；
  - success checkpoint、failure history、resume/force；
  - 最终 `mentor_results.jsonl`；
  - 十个 Sheet 的 `mentor_review.xlsx`。

- `tests/test_batch_extract.py`
  - temp Excel、temp output、fake HTTP、checkpoint、resume 和 workbook 测试。

- `docs/stage5_completion_report.md`

### 修改

- `requirements.txt`
  - 显式增加 `requests>=2.31,<3.0`。

本阶段没有修改模型抽取逻辑、Schema、Stage 2 Excel 读取逻辑或 Stage 4 HTTP handler。

## 3. 使用方式

### 只读 dry-run

```powershell
conda activate tutor
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --dry-run
```

dry-run 只读取 Excel、构造 `MentorInput` 并打印 summary，不创建 output 目录，不调用 HTTP。

### 三条 smoke

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 3 `
  --output-dir outputs/stage5_smoke
```

### 继续到十条

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --limit 10 `
  --resume `
  --output-dir outputs/stage5_smoke
```

### 全量候选命令

```powershell
python batch_extract.py `
  --input "职优越导师资料（最新）.xlsx" `
  --resume `
  --output-dir outputs/full_run
```

本阶段没有执行十条或全量真实导师调用。

## 4. CLI 参数

- `--input` / `-i`：必需，源 Excel；
- `--output-dir`：默认 `outputs`；
- `--base-url`：默认 `http://127.0.0.1:9000`；
- `--limit`：最多选择前 N 条有效导师；
- `--offset`：跳过前 N 条有效导师；
- `--resume`：跳过 checkpoint 中相同 `mentor_id + record_hash` 的合法成功记录；
- `--force`：即使有 checkpoint 也重新处理；
- `--dry-run`：不调用接口、不写正式结果；
- `--timeout`：默认 120 秒；
- `--max-retries`：默认 2，表示初次请求之外最多再重试两次；
- `--retry-sleep`：默认 1 秒；
- `--no-excel`：不生成审阅 Excel；
- `--verbose`：额外打印非敏感 summary。

`--resume` 和 `--force` 由 argparse 互斥组强制互斥。limit/offset 均作用于 Stage 2 过滤后的有效 `MentorInput`，不按 Excel 原始行号切片。

## 5. HTTP 请求和错误分类

请求固定为：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "<MentorInput JSON>"
    }
  ],
  "stream": false
}
```

目标地址：

```text
{base_url}/openai/v1/chat/completions
```

成功路径严格读取 `choices[0].message.content`，解析 JSON，通过 `MentorResult` Pydantic 校验，并额外验证返回的 `mentor_id` 和 `record_hash` 与请求一致。

已实现错误类型：

- `http_request_failed`；
- `http_status_error`；
- `invalid_response_shape`，包括 AgentRunServer error JSON；
- `missing_message_content`，包括空 content；
- `invalid_mentor_result_json`；
- `mentor_result_validation_failed`；
- `timeout`；
- `connection_error`；
- `unexpected_error`；
- `excel_invalid_row`。

HTTP 4xx 默认不重试；429、5xx、连接/超时、响应结构和结果校验错误可在上限内重试。失败达到上限后只记录该行并继续下一条。

## 6. Checkpoint 和 resume

成功记录即时追加到：

```text
outputs/checkpoints/success_rows.jsonl
```

每行是完整 `MentorResult`，每次 append 后立即 `flush()`。

resume 跳过必须同时满足：

1. 启用 `--resume`；
2. checkpoint 行能通过 `MentorResult` 校验；
3. `mentor_id` 相同；
4. `record_hash` 与当前 Excel 相同。

以下情况不会跳过：

- `--force`；
- 当前 hash 变化；
- checkpoint 行损坏；
- 只有失败历史；
- 当前 Excel 行无效或重复。

损坏 checkpoint 只按行号输出 warning，不打印损坏内容，并继续处理。

批处理结束后，程序以当前 Excel 的输入顺序和 `mentor_id + record_hash` 从 checkpoint 选择结果，生成：

```text
outputs/mentor_results.jsonl
```

旧 hash 不会进入当前结果。如果本轮对当前 hash 强制重跑后失败，即使历史 checkpoint 有相同 hash 的旧成功，该记录也会从本轮最终 JSONL 排除，避免伪装成当前成功。

## 7. failed_rows.jsonl

每条失败立即追加并 flush，字段为：

- `mentor_id`；
- `record_hash`；
- `source_file`；
- `source_sheet`；
- `source_row`；
- `error_type`；
- `sanitized_error_message`；
- `attempt_count`；
- `failed_at`；
- `retriable`；
- `stage`。

V1 默认不在失败记录中复制 `original_fields`，以减少私有数据扩散。HTTP body、message content 和完整模型响应也不会写入失败文件。

错误消息使用固定短句、最大长度限制和敏感标签二次脱敏。测试验证 AccessKey、API Key、Authorization、`.env` 和 token 不进入失败文件或进度输出。

## 8. mentor_review.xlsx

使用现有 openpyxl 依赖生成新的工作簿，永不修改源 Excel。包含全部十个 Sheet：

1. 导师总览；
2. 行业标签；
3. 任职经历；
4. 技能；
5. 证书资质奖项；
6. 教育背景；
7. 辅导人群；
8. 职业亮点；
9. 质量问题；
10. 处理失败。

抽取明细按 evidence 展开，包含 mentor_id、导师姓名、raw、normalized、mapping_status、evidence source/quote/match_type、confidence，并附各类别专有字段。

格式包含统一深蓝表头、白色粗体、冻结首行、自动筛选、文本换行、顶部对齐和有上限的列宽。没有公式，不存在计算或公式错误风险。

匿名真实链路生成的工作簿已用 openpyxl 重新打开验证：十个 Sheet 全部存在、均冻结 `A2`，总览/技能/任职经历数据行数正确，最终 JSONL 中三条记录全部重新通过 `MentorResult` 校验。

## 9. 测试

执行：

```powershell
conda activate tutor
python -m pytest -q
```

结果：

```text
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 6.70s
```

Stage 5 fake HTTP 测试覆盖：

- dry-run 不调用 HTTP、不写 outputs；
- limit/offset 基于有效记录；
- 请求固定 `stream=false`；
- success checkpoint 即时落盘；
- 单条失败不中断后续记录；
- retriable 失败后成功；
- resume 命中跳过；
- hash 变化后重跑；
- force 失败不复用旧成功；
- 损坏 checkpoint 行继续；
- HTTP 500；
- AgentRunServer error JSON；
- 缺少/空 message content；
- content 非 JSON；
- MentorResult 校验失败；
- response 不是 JSON；
- 最终 JSONL；
- 十个 Sheet 审阅 Excel；
- 原始 Excel 字节不变；
- 敏感错误不泄露；
- resume/force CLI 互斥。

## 10. Smoke 检测结果

### 真实 Excel dry-run

真实文件只读检测成功：

```text
valid_mentor_count: 121
selected_count: 3
dry_run: true
HTTP calls: 0
outputs written: 0
```

### 为什么没有发送真实三条导师资料

尝试真实 `--limit 3` 前，安全审查指出：虽然请求地址是 `127.0.0.1`，Stage 4 服务会继续把导师内容发送到 `.env` 指定的模型后端；当前会话无法验证该后端是否属于受信任的数据边界。因此没有把真实导师资料发给该后端。

如需继续真实导师 smoke，需要用户在知悉此数据流后明确确认模型后端可以接收这些私有导师资料。

### 匿名合成真实 HTTP/model smoke

为安全验证完整链路，创建了三条匿名合成 `MentorInput`。

现有 9000 服务上的首次匿名测试：

```text
success: 0
failed: 3
error_type: invalid_mentor_result_json
```

原因是 9000 进程在 Stage 4 代码更新前已经启动，仍运行旧通用 agent 入口，返回的 content 不是 `MentorResult` JSON。

随后不打断现有 9000 进程，在 9001 临时启动当前 Stage 4 代码并再次测试：

```text
selected_count: 3
success_count: 3
failed_count: 0
final_result_count: 3
latency_ms: 32511, 28792, 41588
checkpoint_lines: 3
final JSONL records: 3
review workbook sheets: 10
```

停止临时 9001 服务后再次使用 `--resume`：

```text
skipped_resume_count: 3
HTTP calls: 0
final_result_count: 3
```

这验证了当前代码的真实 AgentRun/model 链路以及断点续跑。临时 9001 进程已经停止，原有 9000 进程未被修改或停止。

所有 smoke 产物位于已被 `.gitignore` 排除的 `outputs/stage5_synthetic_smoke/`。

## 11. 当前限制

- 逐条同步处理，没有并发；
- `failed_rows.jsonl` 和 success checkpoint 是追加历史，不自动压缩；
- 最终 JSONL 在批处理正常结束时重建，中途终止时依靠 checkpoint 恢复；
- 真实导师数据尚未发送到模型后端；
- 现有 9000 服务需要重启，才能加载当前 Stage 4 代码；
- 审阅 Excel 是面向人工筛查的 V1 表格，没有图表或复杂公式；
- 没有执行十条或 121 条全量真实模型调用。

## 12. 下一阶段建议

进入 Stage 6 前建议：

1. 确认 `.env` 指向的模型后端获准接收导师私有数据；
2. 重启 9000 服务以加载当前 Stage 4 代码；
3. 对真实 Excel 运行 `--limit 3`；
4. 人工检查三条的组织关系、证书、evidence 和质量问题；
5. 再使用同一 output 目录运行 `--limit 10 --resume`；
6. 人审通过后才考虑全量 121 条；
7. 对 unmapped、ambiguous、loose evidence 和失败类型做质量汇总。
