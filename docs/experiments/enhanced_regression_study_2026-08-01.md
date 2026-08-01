# Enhanced Regression Study - 2026-08-01

## 目的

本实验用于分析：为什么加入 Skill Graph / failure pattern / recovery tools 后，`enhanced` Agent 在部分数据集上反而比 `baseline` 差。

所有测试均走 openJiuwen `ReActAgent` 主链路，并使用真实 DeepSeek API：

- 模型：`deepseek-v4-flash`
- API Key：仅通过环境变量传入，未写入仓库
- 输出目录：`outputs/regression_study/` 与 `outputs/agentbench/`

## 测试数据集

| 数据集 | 类型 | 任务数 | 说明 |
| --- | --- | ---: | --- |
| `datasets/tasks.jsonl` | 本地 simple | 9 | AI4Science / finance / industrial 普通流程任务 |
| `datasets/challenge_tasks.jsonl` | 本地 hard | 9 | 带 fault_profile、expected_recovery_steps、rollback 的故障恢复任务 |
| AgentBench DBBench `db_out_new` | 公开 benchmark | 100 | 可执行 fixture 过滤，`max_iterations=4` |
| AgentBench DBBench `db_out_new` | 公开 benchmark | 20 | 可执行 fixture 过滤，`max_iterations=8` |

## 运行命令

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
.venv/bin/python -m knowledge_agent.evaluation.openjiuwen_runner \
  --agent all \
  --dataset datasets/tasks.jsonl \
  --output-dir outputs/regression_study/simple \
  --limit 10 \
  --max-iterations 6
```

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
.venv/bin/python -m knowledge_agent.evaluation.openjiuwen_runner \
  --agent both \
  --dataset datasets/challenge_tasks.jsonl \
  --output-dir outputs/regression_study/challenge \
  --limit 9 \
  --max-iterations 6
```

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --split db_out_new \
  --limit 100 \
  --require-executable-fixture \
  --max-iterations 4
```

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --split db_out_new \
  --limit 20 \
  --require-executable-fixture \
  --max-iterations 8 \
  --output-dir outputs/regression_study/agentbench_db_out_new_20_iter8
```

## 结果汇总

### 本地 simple tasks

| Agent | success_rate | key_step_f1 | required_order | avg_tool_calls | avg_latency_ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 1.000 | 1.000 | 1.000 | 6.778 | 16035.222 |
| rag | 0.889 | 0.990 | 0.889 | 7.111 | 14999.778 |
| memory | 1.000 | 1.000 | 1.000 | 6.778 | 11498.222 |
| enhanced | 0.667 | 0.970 | 0.667 | 9.333 | 18656.222 |

诊断：

- enhanced 9/9 条任务都选中了 skill。
- enhanced 触发 `retrieve_skills` 13 次，触发 `record_trace_step` 42 次。
- simple tasks 没有真实 fault/recovery 需求，因此 `retrieve_skills` 与 `record_trace_step` 主要变成额外开销。
- enhanced 的 required order 从 1.0 降到 0.667，说明额外工具和计划步骤干扰了原本较短的领域工具顺序。

### 本地 challenge tasks

| Agent | success_rate | key_step_f1 | recovery_rate | rollback_used | required_order | avg_tool_calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.000 | 0.891 | 0.000 | 0.000 | 0.333 | 7.556 |
| enhanced | 0.333 | 0.849 | 1.000 | 0.111 | 0.333 | 11.000 |

诊断：

- baseline 能检测到 fault，但没有 recovery tools，因此 recovery_rate 为 0。
- enhanced 9/9 条任务都选中了 skill，并且 9/9 条任务完成 recovery。
- enhanced 成功率从 0 提升到 0.333，说明知识增强模块在故障恢复类任务上有效。
- enhanced key-step F1 略降，原因是 recovery tools 增加了非 expected key steps，且部分任务虽恢复了 fault，但没有完整满足 required order。

### AgentBench DBBench 100 tasks, max_iterations=4

| Agent | official_success_rate | task_success_rate | avg_tool_calls | avg_latency_ms | max_iter_raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.790 | 0.810 | 6.900 | 6836.570 | 54 |
| enhanced | 0.720 | 0.750 | 9.000 | 10679.080 | 87 |

诊断：

- enhanced 100/100 条任务都调用了 `retrieve_skills`，100/100 条 selected skills 非空。
- enhanced 比 baseline 多 2.1 次平均工具调用，平均延迟增加约 3.84 秒。
- `max_iterations=4` 下，enhanced 出现更多 raw final max-iteration 输出。虽然 scorer 已优先使用 `answer_submitter` 的提交答案，但更多未完成 final 仍说明 ReAct 预算紧张。
- DBBench 是纯 SQL QA，当前 skill plan 只提供通用步骤，并没有带来 SQL 生成或 schema linking 的实质信息增益。

### AgentBench DBBench 20 tasks, max_iterations=8

| Agent | official_success_rate | task_success_rate | avg_tool_calls | avg_latency_ms | max_iter_raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 1.000 | 1.000 | 7.100 | 9532.200 | 0 |
| enhanced | 1.000 | 1.000 | 9.450 | 14776.250 | 0 |

诊断：

- 放宽到 `max_iterations=8` 后，baseline 和 enhanced 都达到 1.0。
- enhanced 仍平均多 2.35 次工具调用，延迟增加约 5.24 秒。
- 这说明 DBBench 上的退化主要来自 ReAct 预算/开销；预算充足时不一定降低准确率，但仍明显降低效率。

## 为什么 enhanced 会变差

### 1. 固定前置 `retrieve_skills` 对简单任务是负收益

enhanced prompt 要求每题先调用 `retrieve_skills`。在 simple tasks 和 DBBench 这类无故障任务中，检索出来的是通用流程模板，不能提供新的领域信息，却消耗一次 ReAct step、增加 prompt 上下文和工具 observation。

### 2. 工具集合膨胀增加了选择难度

baseline 在 DBBench 只有 3 个工具：

- `db_schema_reader`
- `sql_query_executor`
- `answer_submitter`

enhanced 在 DBBench 有 11 个工具，普通三域任务可到 13-14 个工具。LLM 需要在更多工具中选择，容易多调用 `record_trace_step`、重复 validate，或把 recovery 工具误当成普通流程工具。

### 3. 当前 Skill Graph 对纯 SQL QA 的信息增益不足

DBBench 成败主要取决于：

- schema linking
- SQL 聚合/过滤/排序
- 表格值匹配
- 最终答案抽取

当前 DBBench seed skill 只描述 `read_schema -> generate_sql -> execute_sql -> validate_answer -> submit_answer`，没有提供可执行 SQL 模板、字段别名映射、聚合模式库、日期/数值规范化规则。因此它增加了步骤，但没有提升 SQL 质量。

### 4. failure pattern 与 rollback 的优势只在 hard tasks 出现

challenge tasks 显示 enhanced 的 recovery_rate 从 0 提升到 1.0，rollback_used 从 0 提升到 0.111。说明模块本身有效，但适用场景偏向：

- 工具失败
- 输入缺失
- policy/risk 冲突
- runbook mismatch
- rollback before health check

对没有 failure/recovery 的普通任务，模块应该按需启用，而不是固定启用。

### 5. 评测指标会惩罚额外 recovery/action step

当前 key-step F1 使用 expected steps 与 executed steps 集合比较。enhanced 的 recovery/action step 会增加 predicted set，导致 precision 下降，即使任务行为更安全。这在 challenge tasks 中导致 enhanced key-step F1 从 0.891 降到 0.849。

### 6. ReAct final 与工具提交答案需要分开处理

DBBench 早期结果曾被 `Max iterations reached` 低估。已修正为优先使用 trace 中 `answer_submitter` 的 `submit_answer` observation 作为 final answer。修正后 100 条 DBBench 从 enhanced 0.15 恢复到 0.72，但仍低于 baseline 0.79。

## 结论

当前 enhanced 不是“完全无效”，而是“适用条件不够精细”：

- 在故障恢复任务上：有效，recovery_rate 明显提升。
- 在简单流程任务上：负收益，主要破坏 required order 并增加工具调用。
- 在公开 SQL QA 上：预算充足时准确率不输，但效率更差；预算紧时准确率也下降。

## 建议修复方向

1. 增加 gating：只有当任务包含 fault/risk/unknown context，或 baseline 首轮失败时，才启用 full enhanced。
2. DBBench 使用 SQL-specialized enhanced：保留 schema/SQL/answer 三工具，只把 skill plan 压缩成 system hint，不注册 recovery 全工具集。
3. 禁止 enhanced 在无 fault 时调用 `record_trace_step`，减少无效工具调用。
4. 将 `retrieve_skills` 改成内部 planner 预处理，而不是 ReAct tool call，避免占用模型迭代预算。
5. 根据 domain 配置 tool allowlist：DBBench 不应暴露 rollback/manual escalation 等非 SQL 工具。
6. key-step F1 分开统计 domain steps 与 recovery steps，避免把正确恢复行为误算为 key-step 噪声。
7. 对 DBBench 增加字段别名、聚合模式、SQL repair skill，而不是通用流程 skill。

