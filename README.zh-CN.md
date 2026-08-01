# Agent SOW

中文 | [English README](README.md)

Agent SOW 是一个基于 openJiuwen 的知识强化 Agent 原型项目，对应“知识强化 Agent”SOW 的工程实现。当前主执行链路基于 openJiuwen `ReActAgent`，并支持通过 DeepSeek 兼容 API 进行真实模型调用。

项目目标不是做一个完整生产级 Agent 平台，而是在有限时间内实现可运行、可复现、可评测的工程闭环：

```text
任务输入 -> openJiuwen ReActAgent -> 工具调用 -> 轨迹记录
      -> 技能提炼 -> Skill Graph 检索 -> 知识增强规划 -> 执行反馈更新
```

## 项目亮点

- 主链路严格基于 openJiuwen `ReActAgent`。
- 默认模型为 `deepseek-v4-flash`，API Key 只从环境变量读取。
- 支持 baseline、RAG、memory、enhanced 四种 Agent 模式。
- enhanced 模式支持 Skill Graph 检索、结构化 skill plan、failure pattern、恢复工具、trace 记录和技能置信度更新。
- 内置 AI4Science、金融、工业/运维三类模拟任务。
- 已接入 AgentBench DBBench，作为第一条公开 Benchmark 路径。
- 评测会输出 JSON 结果、Markdown 报告、Skill Graph 和完整 trace。
- `.venv/`、`outputs/`、`logs/`、`external/AgentBench/` 和 API Key 均不会进入 Git。

## 当前状态

这是一个可运行的研究原型。它已经能展示“任务执行 -> 轨迹 -> 技能 -> 图谱 -> 检索增强 -> 反馈更新”的完整闭环，但还不是生产级系统。

## 已完成清单

### openJiuwen 主链路

- 已实现 `OpenJiuwenKnowledgeAgent`。
- 使用 openJiuwen `ReActAgent` 作为主执行框架。
- 使用 `agent.invoke()` 作为主调用路径。
- 从环境变量读取：
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_MODEL`
  - `DEEPSEEK_API_BASE`
- baseline 和 enhanced 使用同一套 openJiuwen runtime 和同一模型。

### 知识增强执行

- enhanced 模式会注册并调用 `retrieve_skills`。
- `retrieve_skills` 从 Skill Graph 检索相关技能。
- 检索结果会编译成 `skill_plan`，包含：
  - `ordered_steps`
  - `failure_patterns`
  - `rollback_steps`
  - `preconditions`
  - `required_tools`
  - `known_constraints`
  - `plan_warnings`
  - `blocked_reasons`
- enhanced prompt 明确要求先检索技能，再执行领域工具。
- enhanced 工具集中包含：
  - `retrieve_skills`
  - `record_trace_step`
  - `update_skill_feedback`
  - `export_skill_graph`
  - `context_requester`
  - `alternative_tool_selector`
  - `rollback_executor`
  - `manual_escalation`

### Trace 与反馈闭环

- 已实现统一 trace schema。
- trace 会记录：
  - task id
  - domain
  - model
  - agent type
  - registered tools
  - tool calls
  - observations
  - errors
  - expected steps
  - selected skills
  - recovery flags
  - latency
- seed traces 可以被提炼为技能。
- 运行结束后会根据成功/失败更新技能置信度和 evidence trace id。

### Skill Graph

- 已实现轻量级内存 Skill Graph。
- 支持 JSON 导出。
- 支持 skill、tool、domain、failure mode 等节点关系。
- 检索时会考虑：
  - domain 是否匹配
  - confidence
  - task/context 关键词重合
  - failure pattern 是否命中

### 领域工具

- AI4Science：
  - 文献检索
  - 论文变量抽取
  - 输入校验
  - 实验/分析方案设计
  - 约束检查
  - 报告生成
- 金融：
  - 单据解析
  - 政策检查
  - 风险扫描
  - 证据收集
  - 审批/拒绝决策
- 工业/运维：
  - 告警读取
  - 日志检索
  - 根因分析
  - runbook 选择
  - 健康检查
  - incident report
- 恢复工具：
  - 缺失上下文恢复
  - 替代路径选择
  - 回滚执行
  - 人工升级

### Challenge Benchmark

- `datasets/challenge_tasks.jsonl` 已包含 hard tasks。
- 每条 hard task 支持：
  - `fault_profile`
  - `expected_steps`
  - `expected_recovery_steps`
  - `required_before_report`
  - `constraints`
  - `tags`
- baseline、RAG、memory、enhanced 可以在同一任务集上比较。
- 已支持指标：
  - success rate
  - key-step F1
  - average interactions
  - average tool calls
  - recovery rate
  - failure detection rate
  - rollback used rate
  - required order rate
  - latency
  - estimated token usage

### AgentBench 公开 Benchmark

- 已新增 AgentBench 外部安装脚本。
- AgentBench 源码会克隆到 `external/AgentBench`，不会进入 Git。
- 已接入 AgentBench DBBench 数据：
  - `external/AgentBench/data/dbbench/dev.jsonl`
  - `external/AgentBench/data/dbbench/db_out_new.jsonl` 等更大的公开文件
- 已实现 DBBench adapter，将公开数据转换为项目统一 task 格式。
- 已新增 DBBench 工具：
  - `db_schema_reader`
  - `sql_query_executor`
  - `answer_submitter`
- DBBench baseline/enhanced 评测产物写入 `outputs/agentbench/`。

### 测试

- 单元测试已覆盖：
  - trace roundtrip
  - skill extraction/store/graph
  - openJiuwen tool set
  - fault profile 与 recovery tool
  - AgentBench adapter
  - DBBench SQL fixture
  - mock AgentBench runner
- 已进行 DeepSeek 真实 API smoke test。
- 已进行 AgentBench DBBench 真实 API smoke test 和 100 条小规模公开集测试。

## 最近一次公开 Benchmark 验证结果

最近一次公开数据集小规模测试使用 AgentBench DBBench `db_out_new`，并开启 100 条可执行 fixture 过滤。该过滤只保留“官方 gold SQL 在本地从 AgentBench task record 重建的 SQLite fixture 上能够返回 expected label”的记录。

```bash
DEEPSEEK_MODEL=deepseek-v4-flash
bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --split db_out_new \
  --limit 100 \
  --require-executable-fixture \
  --max-iterations 4
```

真实 DeepSeek API 测试结果：

| Agent | official_success_rate | task_success_rate | avg_turns | avg_tool_calls | avg_latency_ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.79 | 0.81 | 6.9 | 6.9 | 6836.57 |
| enhanced | 0.72 | 0.75 | 9.0 | 9.0 | 10679.08 |

trace 检查结果：

- 模型为 `deepseek-v4-flash`
- baseline 任务数：100
- enhanced 任务数：100
- enhanced `retrieve_skills` 调用次数：100
- enhanced selected skills 非空任务数：100

结论：openJiuwen + Skill Graph 的知识增强链路已经完整跑通，但在这组纯 SQL DBBench 任务上没有体现正向提升。enhanced 会额外消耗一次 ReAct 技能检索，并带来更高的平均交互轮数和工具调用次数。当前知识增强路径在带故障、恢复步骤、回滚决策的 hard tasks 上更有优势；若要在公开 SQL QA 上取得稳定提升，还需要继续做 DBBench 专用 prompt 和迭代预算优化。

另外，较早的 DBBench dev smoke 在 `dev_1` 上 baseline/enhanced 均达到 `official_success_rate=1.0`。`dev_0` 可以从官方 dev 文件正常加载，但可见 table fixture 中不包含 gold 条件，因此更适合作为工具链 smoke case，而不是效果样本。

## 未完成清单

### AgentBench 官方 scorer

- 当前 DBBench 评测读取 AgentBench dev 数据，并使用本项目本地 fixture/answer matcher 判分。
- 还没有接入 AgentBench 官方 server-side result processor 作为最终 scorer。

### AgentBench 完整环境

- 当前只接入 DBBench。
- 尚未接入：
  - OS
  - KG
  - WebShop
  - ALFWorld
  - Mind2Web
  - Avalon
  - LTP
  - card game

### DBBench 官方后端

- 当前 SQL 执行使用从 AgentBench task record 重建的 SQLite fixture。
- 尚未使用 AgentBench 原生 MySQL/Docker session 作为 DBBench 执行环境。

### 生产级能力

- 尚未实现：
  - 多租户权限
  - auth
  - 沙箱策略管理
  - 队列
  - 分布式执行
  - 灰度发布
  - 完整观测平台

### Benchmark 严谨性

- challenge tasks 是可控模拟任务，适合工程验证，但不等同于公开 Benchmark 大规模结论。
- 公开 Benchmark 还需要更多任务、多次运行和统计置信度。

### Token 统计

- openJiuwen 日志中包含 token usage。
- 当前部分 evaluation 指标仍使用估算 token 字段，尚未统一解析全部 openJiuwen 日志。

### SQL recovery 公开评测

- 已有 recovery tools 和 SQL failure pattern。
- 但尚未构建专门的公开 DBBench SQL failure/recovery 子集。

## 目录结构

```text
agent-sow/
├── knowledge_agent/
│   ├── openjiuwen_agent/      # openJiuwen ReAct 主链路与工具注册
│   ├── benchmarks/            # AgentBench adapter
│   ├── evaluation/            # 评测 runner 与指标
│   ├── tracing/               # trace schema 与 JSONL IO
│   ├── skills/                # skill schema、提炼器、持久化存储
│   ├── graph/                 # 轻量 Skill Graph
│   └── feedback/              # 技能置信度与证据链更新
├── datasets/
│   ├── tasks.jsonl
│   ├── challenge_tasks.jsonl
│   ├── seed_traces.jsonl
│   └── agentbench_seed_traces.jsonl
├── demos/
├── scripts/
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

## 环境要求

- Python 3.10+
- openJiuwen
- DeepSeek-compatible API Key
- Docker，用于后续 AgentBench 原生环境

## 安装

```bash
cd /mnt/huawei/ymb/agent-sow
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[openjiuwen,dev]"
```

如果 `.venv` 中已经安装了 openJiuwen，可以直接复用当前环境。

## 环境变量

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_MODEL="deepseek-v4-flash"
export DEEPSEEK_API_BASE="https://api.deepseek.com"
```

请不要把 API Key 写入源码、脚本、README 或输出文件。

## 快速开始

检查 openJiuwen：

```bash
bash scripts/check_openjiuwen.sh
```

DeepSeek API smoke test：

```bash
DEEPSEEK_API_KEY=... .venv/bin/python scripts/test_deepseek_api.py
```

openJiuwen smoke test：

```bash
DEEPSEEK_API_KEY=... bash scripts/test_openjiuwen_deepseek.sh
```

运行 demo：

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_demo.sh
```

运行默认任务集上的 baseline/enhanced 对比：

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh --agent both --limit 3
```

运行 hard challenge 全模式评测：

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh \
  --agent all \
  --dataset datasets/challenge_tasks.jsonl \
  --limit 9
```

## AgentBench DBBench

克隆 AgentBench 到外部目录：

```bash
bash scripts/setup_agentbench.sh
```

运行 DBBench baseline/enhanced 对比：

```bash
DEEPSEEK_API_KEY=... bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --limit 1 \
  --max-iterations 6
```

运行一个已验证可成功的 DBBench dev task：

```bash
DEEPSEEK_API_KEY=... bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --offset 1 \
  --limit 1 \
  --max-iterations 6
```

输出位置：

```text
outputs/agentbench/
├── agentbench_db_results.json
├── agentbench_db_results_baseline.json
├── agentbench_db_results_enhanced.json
├── agentbench_db_report.md
└── traces/
```

## Agent 模式

| 模式 | 说明 |
| --- | --- |
| `baseline` | 经典 ReAct，只使用领域工具，不使用技能检索。 |
| `rag` | ReAct + 静态参考文档，不使用 Skill Graph 或 rollback plan。 |
| `memory` | ReAct + 原始历史轨迹摘要，不使用结构化技能。 |
| `enhanced` | ReAct + Skill Graph + skill plan + recovery tools + feedback update。 |

## 测试

运行轻量测试：

```bash
.venv/bin/python tests/run_tests.py
```

或使用 pytest：

```bash
.venv/bin/python -m pytest
```

## Git 与产物策略

以下内容不会进入 Git：

- `.venv/`
- `outputs/`
- `logs/`
- `external/AgentBench/`
- Python cache
- build artifacts
- API Key

AgentBench 源码只放在 `external/AgentBench`，作为外部依赖管理。

## License

当前尚未添加明确许可证。公开发布为正式开源项目前，应补充 `LICENSE` 文件。
