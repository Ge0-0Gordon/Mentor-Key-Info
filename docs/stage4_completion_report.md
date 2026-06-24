# 阶段 4 完成报告：OpenAI-compatible 本地接口接入

## 1. 阶段结论

阶段 4 已完成。`main.py` 现在是单导师抽取的薄入口：从最后一条 `role=user` 消息的 `content` 解析 `MentorInput`，在 `stream=false` 下直接调用 AgentRun LangChain-compatible `model_client` 和 Stage 3 `extract_single_mentor`，最后向 `AgentRunServer` 返回 `MentorResult` JSON 字符串。

`AgentRunServer` 继续负责 `/openai/v1/chat/completions` 协议和 `choices[0].message.content` 包装。代码没有手工构造 OpenAI choices，也没有让模型直接生成 `MentorResult`。

## 2. 修改文件

### 修改

- `main.py`
  - 创建独立 `model_client`；
  - 解析最后一条 user message；
  - 校验 `MentorInput`；
  - 拒绝导师抽取的 `stream=true`；
  - 直接调用 `extract_single_mentor`；
  - 返回 `result.model_dump_json(by_alias=True)`；
  - 增加不泄露原始内容的错误处理；
  - 使用 `if __name__ == "__main__"` 保持 `python main.py` 启动方式，同时允许离线导入测试。

### 新增

- `tests/test_main_stage4.py`
  - 使用 fake AgentRun model factory 和 fake error paths 测试请求处理；
  - 不连接真实 AgentRun 模型或 HTTP 服务。

- `docs/stage4_completion_report.md`

### 未修改

- `mentor_agent/extractor.py` 的模型/结果职责边界；
- `/openai/v1/chat/completions` 路由；
- AgentRunServer 的 OpenAI-compatible 响应包装；
- `requirements.txt`；
- Excel、批处理和 outputs 逻辑。

## 3. main.py 导师抽取路径

环境变量仍由 `.env`/环境加载：

- `MODEL_SERVICE_NAME`；
- `MODEL_NAME`；
- `SANDBOX_NAME`。

其中 `MODEL_SERVICE_NAME` 必填。模型客户端只创建一次：

```python
model_client = model(MODEL_SERVICE_NAME, model=MODEL_NAME)
```

非流式请求处理流程：

```text
AgentRequest
  -> 从后向前找到最后一条 role=user 消息
  -> json.loads(message.content)
  -> MentorInput.model_validate(payload)
  -> extract_single_mentor(mentor_input, model_client, ...)
  -> MentorResult.model_dump_json(by_alias=True)
  -> AgentRunServer 包装到 choices[0].message.content
```

模型只接收 Stage 3 构造的 prompt，并只负责输出 `MentorExtraction`。evidence 校验、normalizer、guardrail 和 `MentorResult` 组装仍全部由程序完成。

## 4. Fallback 选择

阶段 4 没有保留原通用 LangChain Agent fallback，也不再创建 `create_agent(...)`、工具列表或沙箱实例。

原因：当前接口已经有明确的 `MentorInput -> MentorResult` 契约。如果普通文本、坏 JSON 或非法 `MentorInput` 自动进入通用 agent，会：

- 掩盖调用方格式错误；
- 让无效请求意外触发模型或工具；
- 引入通用 system prompt 与抽取 prompt 的职责冲突；
- 使错误路径难以稳定测试。

因此非导师输入明确失败。`SANDBOX_NAME` 仍被读取以保持现有环境变量兼容，但导师抽取路径不使用沙箱。

## 5. stream=true 规则

V1 不支持导师结构化抽取流式响应。

当最后一条 user content 是合法 `MentorInput` 且 `stream=true` 时，入口会在调用模型前返回明确错误：

```text
stream=true is not supported for mentor extraction; use stream=false
```

没有静默降级成非流式，也不会调用模型。阶段 5 批处理应固定使用 `stream=false`。

## 6. 错误处理与日志安全

入口定义 `Stage4RequestError`，错误消息只包含固定说明或验证错误数量，不包含 Pydantic 的完整输入详情。

处理范围：

- 没有 user message：明确拒绝；
- user content 不是字符串：明确拒绝；
- content 不是合法 JSON：明确拒绝；
- JSON 不是合法 `MentorInput`：只返回 validation error 数量；
- `stream=true`：明确要求 `stream=false`；
- `ExtractionError`：对外统一为 `mentor extraction failed`；
- 其他模型/服务异常：对外统一为 `model service call failed`。

日志只写固定事件名称，不拼接异常对象、消息 content、导师全文或 Pydantic 输入。代码中已移除 `print`、`traceback.print_exc` 和原始异常文本日志。

测试验证异常中即使包含 AccessKey、API Key、Authorization、`.env` 或 token，也不会出现在入口错误消息或本阶段日志调用参数中。

## 7. OpenAI-compatible 协议保持

- 启动方式仍为 `python main.py`；
- `AgentRunServer(invoke_agent=invoke_agent).start()` 仍使用默认 9000 端口；
- `/openai/v1/chat/completions` 仍由 AgentRunServer 提供；
- 请求继续使用顶层 `messages` 和 `stream`；
- 没有手工构造 `choices`；
- callback 返回字符串，由 AgentRunServer 放入 `choices[0].message.content`。

新增 `__main__` guard 只避免测试导入时启动服务器，不改变直接执行 `python main.py` 的行为。

## 8. 测试

执行命令：

```powershell
conda activate tutor
python -m pytest -q
```

结果：

```text
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 5.55s
```

Stage 4 新增测试覆盖：

- `model_client` 使用 `MODEL_SERVICE_NAME` 和 `MODEL_NAME` 创建；
- 合法 `MentorInput` 在 `stream=false` 下返回可校验的 `MentorResult` JSON；
- 从多条消息中选择最后一条 user message；
- 缺少 user message；
- 非 JSON content 且不进入 fallback；
- 非法 `MentorInput`；
- `stream=true` 在模型调用前拒绝；
- `ExtractionError` 的敏感内容不泄露；
- 未预期模型服务异常的敏感内容不泄露。

全套 Stage 1-4 测试共 83 项通过。`git diff --check` 通过，仅有 Git 的 CRLF 转换提示。

## 9. 真实 HTTP smoke test

本阶段没有执行真实 HTTP smoke test，也没有新增 smoke 脚本。真实测试需要用户本地 `.env` 中的有效 AgentRun 模型配置并启动 `python main.py`；离线 pytest 已通过 fake model 覆盖入口和抽取集成，不将真实服务可用性作为单元测试前提。

## 10. 当前限制

- 只支持单导师 `stream=false`；
- 接口不再处理普通聊天文本；
- 未实现 HTTP 层自定义错误状态或错误 JSON，错误响应仍由 AgentRunServer 统一处理；
- 未进行真实模型质量与延迟验证；
- 未实现批处理、checkpoint、失败行记录或结果导出；
- `SANDBOX_NAME` 仅为配置兼容保留，当前路径不使用。

## 11. 下一阶段建议

阶段 5 可以实现 `batch_extract.py`：

1. 复用阶段 2 `load_mentor_inputs_with_report`；
2. 逐条以 `stream=false` 调用本地 `/openai/v1/chat/completions`；
3. 每条成功后立即写 checkpoint；
4. 失败行写独立、可重试的失败记录；
5. 按 `mentor_id + record_hash` 实现断点续跑；
6. 全部完成后再组装最终 JSONL 和人工审阅 Excel；
7. 保持真实模型失败显式，不添加静默 mock fallback。
