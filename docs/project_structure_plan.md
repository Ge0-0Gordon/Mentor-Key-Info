# 项目结构整理与后续前后端拆分建议

## 本次整理目标

本项目当前既是 AgentRun 本地服务壳，也是导师抽取、批处理和匹配推荐的业务原型。为了后续继续接数据库和前端，目录需要做到两点：

1. 根目录保留少量稳定入口，避免脚本和临时产物散落。
2. 业务核心逻辑尽量留在 `mentor_agent/`，不要绑死在 AgentRun、CLI 或未来 Web API 上。

## 当前建议结构

```text
agentrun-mentor-info/
  mentor_agent/             # 业务核心：Excel、抽取、simple/full schema、匹配排序
  configs/                  # alias、prompt、匹配配置等可编辑配置
  scripts/                  # 检查、benchmark、开发辅助脚本
    dev/                    # 临时调试脚本
  docs/                     # 阶段报告、设计说明、运行手册
  tests/                    # pytest
  outputs/                  # 本地生成产物，不提交 Git
    runs/                   # 正式/半正式批处理运行结果
    eval/                   # 模型或方案评估结果
    benchmarks/             # benchmark 原始输出
    reports/                # 可读报告、summary
    matching_embeddings/    # 本地 embedding/cache
    archive/                # 旧实验归档
  main.py                   # AgentRun/OpenAI-compatible 本地服务入口
  batch_extract.py          # Excel 批量抽取 CLI 入口
  match_mentors.py          # 导师推荐匹配 CLI 入口
```

根目录目前保留 `main.py`、`batch_extract.py`、`match_mentors.py` 是合理的：它们是用户最常用的三个入口。后续如果服务变复杂，再把它们迁移到 `apps/`。

## 本次输出目录整理规则

`outputs/` 统一按用途分层：

- `outputs/runs/`：批处理抽取结果，例如 `simple_full_run_...`。
- `outputs/eval/`：模型对比、方案评估。
- `outputs/benchmarks/`：延迟测试、rerank 测试等 benchmark 产物。
- `outputs/reports/`：Markdown/JSON summary 报告。
- `outputs/matching_embeddings/`：本地 fake/semantic cache。
- `outputs/archive/`：历史失败重试或暂不需要的旧实验。

`outputs/` 整体仍然被 `.gitignore` 忽略，避免提交真实导师数据、模型响应或本地评估产物。

## 是否应该拆成前后端

建议后续拆，但先不要急着拆成多个仓库。

更稳的做法是保留一个 monorepo：

```text
agentrun-mentor-info/
  mentor_agent/             # 纯业务核心，不依赖前端/数据库/AgentRun
  apps/
    agentrun_server/        # 未来可放 main.py 的 AgentRun 适配层
    api/                    # 未来 FastAPI 后端
    web/                    # 未来前端，例如 Next.js/Vite
  migrations/               # 后续数据库迁移
  configs/
  scripts/
  tests/
  docs/
```

拆分边界建议：

- `mentor_agent/`：领域核心。放 schema、抽取、匹配、打分、alias、导出等逻辑。
- `apps/agentrun_server/`：AgentRun/OpenAI-compatible 协议适配，只负责把 HTTP 请求转成业务函数调用。
- `apps/api/`：未来产品后端，负责用户、导师、推荐接口、数据库读写、鉴权。
- `apps/web/`：未来前端，只展示导师卡片和调用后端 API，不放推荐打分逻辑。

这样做的好处是：AgentRun 只是一个壳，后面就算换成 FastAPI、队列任务或数据库服务，核心匹配逻辑也不用重写。

## 数据库接入建议

第一版仍然可以继续读 `mentor_results.jsonl`，因为导师只有约 121 条，内存全量扫描很快。

当需要数据库时，建议新增：

```text
mentor_agent/storage/       # 仓储接口、JSONL/DB 读取适配
migrations/                 # Alembic 或其他迁移脚本
apps/api/                   # API 层调用 storage + matching
```

不要把数据库 ORM 模型和 Pydantic 输出 schema 混在一起。推荐拆成：

- DB model：负责落库字段、索引、关系。
- Pydantic schema：负责接口输入输出和内部校验。
- repository/storage：负责从 DB 或 JSONL 加载导师资料。

## 现在不建议做的事

- 不把项目立即拆成多个 repo。
- 不把所有 CLI 都搬进深层目录，避免日常命令变难用。
- 不把推荐逻辑放进前端。
- 不把 AgentRun 的 request/response 协议渗透进 `mentor_agent/` 核心模块。
- 不提交 `outputs/`、`.env`、原始 Excel、`python/`。

## 下一步建议

1. 继续保留当前根目录三个入口，先让抽取和匹配稳定。
2. 如果要接数据库，先加 `mentor_agent/storage/`，做 JSONL 与 DB 双实现。
3. 如果要接前端，新增 `apps/api/` 和 `apps/web/`，不要改动现有核心匹配函数。
4. 等 API 稳定后，再考虑把 `main.py` 移到 `apps/agentrun_server/`，根目录保留兼容启动脚本。
