# 阶段 1 完成报告：数据契约与测试样本

## 1. 阶段结论

阶段 1 已完成。项目现在具备版本化的 V1 Pydantic 数据契约、soft industry taxonomy、抽取规则常量、匿名合成测试样本和 Schema 全量测试。

本阶段没有修改 `main.py`，没有读取或处理原始导师 Excel，没有调用模型，没有启用沙箱，也没有接入数据库或批处理。

## 2. 实现文件

### 新增

- `mentor_agent/__init__.py`
  - 建立 mentor_agent 包；
  - 导出阶段 1 的主要数据契约和版本常量。

- `mentor_agent/schemas.py`
  - 定义公共枚举；
  - 定义 MentorInput、MentorExtraction 和 MentorResult；
  - 定义行业、任职经历、技能、证书资质奖项、教育、辅导人群、职业亮点、Evidence、QualityIssue 和 ProcessingMetadata 等子模型；
  - 所有模型使用 `extra="forbid"`。

- `mentor_agent/prompts.py`
  - 固化 PROMPT_VERSION；
  - 固化 INDUSTRY_TAXONOMY_VERSION；
  - 保存 30 类 soft industry taxonomy；
  - 保存 confidence、mapping_status、组织关系、证书和技能规则；
  - 保存匿名正反例。

- `tests/__init__.py`
  - 建立测试包。

- `tests/sample_data.py`
  - 提供匿名合成 MentorInput；
  - 提供完整和最小 MentorResult；
  - 覆盖 employer、client、project、partner 和 unknown；
  - 不复制真实导师完整资料。

- `tests/test_schemas.py`
  - 覆盖阶段 1 Schema 和规则测试。

- `pytest.ini`
  - 将 pytest 发现范围限制为项目 `tests/`；
  - 排除 vendored `python/`、`__MACOSX/` 等目录；
  - 禁用当前工作区不可写的 pytest cache provider。

- `docs/stage1_completion_report.md`
  - 记录阶段 1 实现与验证结果。

### 修改

- `.gitignore`
  - 增加 pytest 临时缓存目录 `pytest-cache-files-*/`；
  - 避免首次测试产生的权限受限临时目录污染 Git 状态。

- `requirements.txt`
  - 显式声明 Pydantic V2 范围；
  - 增加 pytest 测试依赖。

### 未修改

- `main.py`
- `test_request.py`
- 原始导师 Excel
- `.env`

## 3. 依赖变化

requirements.txt 新增：

```text
pydantic>=2.12.4,<3.0.0
pytest>=8.0,<9.0
```

tutor 环境中的实际版本：

- Python 3.10.20；
- agentrun-sdk 0.0.50；
- Pydantic 2.13.4；
- pytest 8.4.2。

AgentRun SDK 和 Pydantic 在安装前已经存在。阶段 1 新安装 pytest 及其缺失的测试运行依赖。

## 4. Schema 覆盖范围

### 三个数据层

- `MentorInput`
  - 单导师任务信息；
  - mentor_id；
  - SHA-256 record_hash；
  - 来源文件、Sheet 和行号；
  - Excel 九个 original_fields。

- `MentorExtraction`
  - industry_tags；
  - career_experiences；
  - skills；
  - credentials_and_awards；
  - education；
  - target_mentees；
  - career_highlights；
  - summary。

- `MentorResult`
  - Schema、Prompt 和 taxonomy 版本；
  - 输入来源与原始字段；
  - normalized_profile；
  - 全部抽取数组；
  - quality_issues；
  - processing metadata。

### V1 强校验

- JSON/Pydantic 结构合法；
- 未声明字段被拒绝；
- confidence 值合法；
- mapping_status 值合法；
- organization relationship 值合法；
- Evidence source_field 只能来自允许的 Excel 字段；
- 行业、技能和公司等核心项必须声明 raw/normalized 字段；
- 语义抽取项至少包含一条 Evidence；
- record_hash 必须是 64 位十六进制字符串；
- ProcessingMetadata 和 MentorResult 不能通过额外字段保存 AccessKey、API Key、Authorization 或 `.env` 内容；
- 所有列表使用独立的 default_factory，缺失时稳定返回空数组。

Evidence 的严格/宽松原文匹配算法属于阶段 3。本阶段只冻结 Evidence 结构、source_field 范围和 match_type 契约。

## 5. 硬枚举与 soft taxonomy

### 硬枚举

- Confidence：high、medium、low；
- MappingStatus：mapped、unmapped、ambiguous；
- OrganizationRelationship：employer、client、project、partner、unknown；
- EmploymentStatus；
- CredentialCategory；
- CredentialStatus；
- SkillCategory；
- EvidenceSourceField；
- EvidenceMatchType；
- QualityIssueSeverity；
- EducationType；
- TargetMenteeDimension。

### 非硬枚举

- `SOFT_INDUSTRY_TAXONOMY` 是普通 tuple 常量，不是 Enum；
- industry_category 是自由字符串或 null；
- taxonomy 外行业可通过 Schema；
- taxonomy 外行业可以使用 `mapping_status="unmapped"`，同时保留 raw_industry；
- raw_skill 是自由字符串，不受固定技能词表限制；
- normalized_skill 允许为空，表示未完成安全归一。

## 6. 匿名测试样本覆盖

测试样本使用完全虚构的导师和组织名称，覆盖：

- 合法 MentorInput；
- 完整 MentorResult；
- 缺省复杂可选字段的最小 MentorResult；
- employer、client、project、partner、unknown 五种关系；
- taxonomy 内行业；
- taxonomy 外 unmapped 行业；
- 自由技能名称；
- 证书资质；
- warning QualityIssue；
- 原始字段中文 alias 序列化。

## 7. 测试

### 用户可执行命令

```powershell
conda activate tutor
python -m pip install -r requirements.txt
python -m pytest -q
```

自动化执行时使用了等价的非交互命令：

```powershell
conda run -n tutor python -m pip install -r requirements.txt
conda run -n tutor python -m pytest -q
```

### 最终结果

```text
...................................                                      [100%]
35 passed in 0.09s
```

共 35 个测试通过，没有失败或跳过。

测试覆盖：

- 合法 MentorInput 和 MentorResult；
- JSON round-trip；
- 合法和非法 confidence；
- 合法和非法 mapping_status；
- 非法 relationship；
- 根对象和嵌套对象 extra 字段；
- optional 复杂字段；
- 列表默认值和默认值隔离；
- soft taxonomy 外行业；
- 自由 raw_skill；
- warning/error QualityIssue；
- 非法 Evidence source_field；
- raw/normalized 核心字段缺失；
- ProcessingMetadata 和结果根对象的敏感额外字段；
- Prompt 版本、taxonomy 数量、规则常量和正反例。

## 8. 遇到的问题和解决方式

### pytest 收集了第三方 vendored 测试

首次执行 `python -m pytest -q` 时，pytest 递归扫描了项目中的 `python/` 和 `__MACOSX/`。这些目录包含第三方包测试和不适用于当前 Windows 环境的 vendored 二进制依赖，导致 20 个测试收集错误。

根因不是本项目 Schema 失败，而是 pytest 默认发现范围过宽。

解决方式：新增 `pytest.ini`，将 testpaths 限制为 `tests`，并排除 `python/`、`__MACOSX/`、`.git` 和缓存目录。这样用户要求的原始命令 `python -m pytest -q` 可以直接运行，无需额外指定测试路径。

### pytest 缓存目录权限警告

首次测试还出现 pytest cache provider 无法创建缓存路径的警告。缓存不影响阶段 1 测试正确性，因此在 pytest.ini 中禁用 cache provider，避免产生无关缓存和警告；同时在 `.gitignore` 中排除该次尝试生成的 `pytest-cache-files-*/` 临时目录。

## 9. 阶段 1 明确未做

- 未修改 main.py 的接口或启动逻辑；
- 未修改 test_request.py；
- 未读取或处理原始导师 Excel；
- 未实现 Excel 行解析；
- 未实现 mentor_id 和 record_hash 生成逻辑；
- 未调用模型；
- 未实现 Agent structured output；
- 未实现 Evidence 严格/宽松匹配算法；
- 未实现标准化和去重代码；
- 未实现 batch_extract.py；
- 未生成 JSONL 或审阅 Excel；
- 未启用沙箱；
- 未接数据库；
- 未执行 Git commit。

## 10. 下一阶段建议

可以进入阶段 2：Excel 与确定性预处理。

阶段 2 建议按以下顺序进行：

1. 增加 openpyxl 依赖；
2. 以只读、data_only 模式读取 `服务导师`；
3. 校验固定九列；
4. 跳过只有序号的空记录；
5. 将 Excel 原值映射到 OriginalFields，禁止覆盖原值；
6. 生成 `service_mentor:{序号}`；
7. 对规范 JSON 计算稳定 SHA-256 record_hash；
8. 检测序号缺失、重复和疑似字段错位；
9. 使用匿名临时工作簿编写测试，不把真实导师数据写入测试文件。
