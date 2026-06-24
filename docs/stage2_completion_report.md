# 阶段 2 完成报告：Excel 与确定性预处理

## 1. 阶段结论

阶段 2 已完成。项目现在可以只读加载 Excel 的“服务导师”Sheet，校验九个业务字段，将有效行稳定转换为 `MentorInput`，并返回跳过行、无效行、重复 ID 和轻量字段错位诊断。

本阶段没有调用 AgentRun 模型或 `/openai/v1/chat/completions`，没有实现完整 `batch_extract.py`，没有修改 `main.py`，没有生成 `mentor_results.jsonl`、`mentor_review.xlsx` 或其他正式 outputs，也没有启用沙箱、接入数据库或上传文件。

## 2. 实现文件

### 新增

- `mentor_agent/excel_io.py`
  - 固定 Sheet 名和九个业务字段；
  - 只读加载 Excel；
  - 校验 Sheet 和表头；
  - 过滤完全空行和仅有序号的空记录；
  - 构造 `OriginalFields` 和 `MentorInput`；
  - 生成稳定 `mentor_id` 和 SHA-256 `record_hash`；
  - 检测缺失序号、重复 ID 和疑似字段错位；
  - 提供简化加载函数与带诊断报告的加载函数。

- `tests/test_excel_io.py`
  - 使用 `pytest` 的 `tmp_path` 创建匿名合成 Excel；
  - 覆盖正常转换、Sheet/字段校验、多余列、空行、缺失序号、重复序号、hash 稳定性、文件名、文本保真、数值类型和错位 warning；
  - 在真实文件存在时执行只读 smoke test，不打印导师全文。

- `scripts/check_excel_stage2.py`
  - 接收 Excel 路径；
  - 只输出非敏感 summary；
  - 不调用模型，不写正式结果。

- `docs/stage2_completion_report.md`
  - 记录阶段 2 实现、依赖和实测结果。

### 修改

- `mentor_agent/schemas.py`
  - `OriginalFields` 的“序号”和“职业年限”允许 `int | float | str | None`，避免把 Excel 中合法数值强制转成字符串。

- `requirements.txt`
  - 增加 `pandas>=2.0,<3.0`；
  - 增加 `openpyxl>=3.1,<4.0`。

- `pytest.ini`
  - 将 pytest 临时目录定向到项目内忽略目录，规避当前 Windows 系统临时目录 ACL 问题。

- `.gitignore`
  - 忽略 `.pytest-tmp-stage2/`。

## 3. 依赖

阶段 2 新增声明：

```text
pandas>=2.0,<3.0
openpyxl>=3.1,<4.0
```

已安装到 `tutor` 环境，实际版本：

- pandas 2.3.3；
- openpyxl 3.1.5；
- pytest 8.4.2；
- Pydantic 2.13.4。

没有引入其他大型依赖。

## 4. Excel 读取与字段校验

- 文件路径由调用方传入，不写死绝对路径；
- 通过 `pandas.read_excel(..., engine="openpyxl", dtype=object)` 读取；
- 默认且固定处理 `服务导师`；
- `source_file` 使用 `Path.name`，只保存文件名；
- 不覆盖、不保存、不修改原工作簿；
- 首先检查 Sheet 是否存在，再检查九个业务字段是否全部存在；
- 缺失 Sheet 或字段时抛出包含缺失项的 `ExcelValidationError`；
- 多余字段允许存在，但不会进入 `OriginalFields` 或 hash；
- 使用 `keep_default_na=False` 避免把文本 `NA`/`N/A` 误当空值，随后只把真正空单元格和空白字符串统一为 `None`。

九个业务字段为：序号、导师姓名、性别、城市、职业年限、可辅导学员职级、行业标签、从业经历、背景经验。

## 5. 行处理规则

### 空行与无效行

- 九个业务字段全部为空：跳过，reason 为 `completely_empty_row`；
- 仅“序号”非空、其他八项全空：跳过，reason 为 `sequence_only_row`；
- 序号为空但存在其他业务内容：记录 `missing_required_source_field` error，不构造 `MentorInput`；
- 同一 `mentor_id` 第二次出现：记录 `duplicate_mentor_id` error，不重复构造 `MentorInput`；
- 导师姓名为空，同时性别、城市或从业经历出现异常长文本：记录 `suspected_column_shift` warning，保留原值供人工核对。

诊断信息只包含行号、问题码、严重度和非敏感说明，不包含导师全文。

### 原始值保留

- `OriginalFields` 只包含九个业务字段；
- 文本换行、分号、竖线等分隔符原样保留；
- 不写入“未知”“暂无”“无”等占位符；
- 空值统一为 `None`；
- 序号和职业年限保留数值或字符串类型，不做破坏性文本化。

## 6. mentor_id 与 record_hash

`mentor_id` 使用：

```text
service_mentor:{序号}
```

姓名不参与 ID。整数值浮点序号只在 ID 副本中格式化为无 `.0` 的形式，`OriginalFields` 本身不被覆盖。

`record_hash` 计算步骤：

1. 只选取九个 `OriginalFields`；
2. 将空值统一为 `None/null`，将 pandas/numpy 标量转为稳定 Python 标量，日期时间转为 ISO 字符串；
3. 使用 `ensure_ascii=False`、`sort_keys=True`、紧凑分隔符和 `allow_nan=False` 生成规范 JSON；
4. 对 UTF-8 字节计算 SHA-256。

hash 不包含 `source_row`、`source_file`、`source_sheet` 或 `mentor_id`。合成测试已验证重复计算一致，任一原始业务字段变化会改变 hash。

## 7. 真实 Excel 只读检测

检测文件：`职优越导师资料（最新）.xlsx`

```text
source_file: 职优越导师资料（最新）.xlsx
sheet: 服务导师
total_rows: 123
valid_mentor_count: 121
skipped_count: 2
invalid_count: 0
duplicate_id_count: 0
row_issue_count: 0
```

两个跳过行均为仅有序号、其他八个业务字段为空的记录。121 个 `MentorInput` 均通过 Pydantic 校验，`mentor_id` 唯一，`record_hash` 非空并可由各自九个原始字段稳定重算。

整个检查只读取工作簿并打印汇总，没有打印导师全文，没有调用模型，也没有写正式抽取结果。

## 8. 测试命令与结果

用户可执行：

```powershell
conda activate tutor
python -m pytest -q
python scripts/check_excel_stage2.py "职优越导师资料（最新）.xlsx"
```

自动化验证使用同一个 `tutor` 解释器的直接路径，等价于激活环境后运行：

```text
................................................                         [100%]
48 passed in 0.85s
```

`git diff --check` 通过，仅有 Git 对 CRLF 转换的提示，没有空白错误。

## 9. 遇到的问题和解决方式

### tutor 环境缺少 Excel 依赖

初始环境没有 pandas。按照阶段 2 授权安装 pandas 和 openpyxl，并同步更新 `requirements.txt`。

### conda run 的中文输出编码错误

`conda run` 在 Windows GBK 控制台转发包含特殊 Unicode 的输出时触发 `UnicodeEncodeError`。解析本身没有失败。验证改用 `C:\Users\GD\.conda\envs\tutor\python.exe` 直接运行，仍然是同一个 `tutor` 环境。

### pytest 系统临时目录 ACL

受限执行环境无法遍历 pytest 默认的用户临时目录，合成 Excel 用例在 `tmp_path` setup 阶段失败。`pytest.ini` 将 basetemp 定向到项目内已忽略目录，并在最终验证时按环境要求非沙箱运行测试。最终 48 个测试全部通过。

### compileall 字节码缓存权限

现有 `__pycache__` 在受限 Windows 进程下不可替换，因此没有把 `compileall` 作为完成标准，也没有删除用户缓存。pytest 已完成模块导入、测试收集和全部业务路径执行，提供了更直接的语法与行为验证。

## 10. 下一阶段建议

阶段 3 可以在保持 `MentorInput` 输入边界不变的前提下，实现单条模型调用、structured output 解析、Evidence 严格/宽松匹配和确定性别名归一。建议继续把真实服务失败显式暴露，不添加静默 mock/fallback，并先用匿名单条样本验证后再进入批处理。
