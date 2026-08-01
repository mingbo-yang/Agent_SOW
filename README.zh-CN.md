# Agent SOW

中文 | [English README](README.md)

Agent SOW 是一个基于 openJiuwen 的知识强化 Agent 原型项目，对应“知识强化 Agent”SOW 的工程实现。当前主执行链路基于 openJiuwen `ReActAgent`，并支持通过 DeepSeek 兼容 API 进行真实模型调用。

## GitHub 项目简介

基于 openJiuwen ReActAgent 的知识强化 Agent 原型，支持 Skill Graph 检索增强、故障恢复、轨迹反馈和 AgentBench DBBench 公开 benchmark 评测。

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

- enhanced 模式会在 ReAct 执行前从 Skill Graph 内部检索相关技能。
- 当前采用 gating 策略：普通任务使用紧凑 SkillPlan hint，带 fault/recovery 的 hard task 才暴露恢复工具；DBBench 在没有通过独立回放验证的 DB 技能时主动 abstain。
- 检索结果会编译成 `skill_plan`，包含：
  - `ordered_steps`
  - `failure_patterns`
  - `rollback_steps`
  - `preconditions`
  - `required_tools`
  - `known_constraints`
  - `plan_warnings`
  - `blocked_reasons`
- 默认不再注册审计型知识工具，避免额外 ReAct 回合和工具选择噪声。
- full enhanced hard task 会按需注册：
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

完整的 100 次测试、运行命令、采样限制和负优化分析见
[`docs/experiments/scaled_benchmark_100_2026-08-01.md`](docs/experiments/scaled_benchmark_100_2026-08-01.md)。

| 评测 | Baseline | Enhanced | 主要结论 |
| --- | ---: | ---: | --- |
| Simple workflow，100 次重复稳定性测试 | 1.000 | 1.000 | 准确率持平，enhanced 少 0.55 次工具调用 |
| Challenge recovery，100 次重复稳定性测试 | 0.000 | 0.680 | enhanced 恢复率为 1.000 |
| AgentBench DBBench，100 条独立公开任务 | 0.920 | 0.890 | 差异不显著，exact McNemar `p=0.581` |

DBBench 结果不能宣称提升。通用 SQL 流程技能的信息增益不足，曾造成额外工具调用和过早提交。最终质量门控会在 DB 技能尚未通过独立回放验证时主动 abstain，并在 enhanced trace 中明确记录该决策。当前结论是：故障恢复任务上有明显收益，公开 SQL QA 上恢复到统计持平，仍需真正的 schema linking、SQL pattern 和 query repair 技能。

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
