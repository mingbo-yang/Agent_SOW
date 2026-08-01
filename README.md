# openJiuwen 知识强化 Agent

这是一个基于 openJiuwen `ReActAgent` 的知识强化 Agent 原型。主链路使用真实 LLM API：

```text
任务输入 -> openJiuwen ReActAgent -> 技能检索/业务工具 -> 轨迹记录 -> 执行反馈 -> 技能更新
```

## 快速运行

```bash
bash scripts/check_openjiuwen.sh
DEEPSEEK_API_KEY=... .venv/bin/python scripts/test_deepseek_api.py
DEEPSEEK_API_KEY=... bash scripts/test_openjiuwen_deepseek.sh
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_demo.sh
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh
python3 tests/run_tests.py
```

## 评测输出

openJiuwen 评测产物位于 `outputs/`：

- `openjiuwen_eval_results.json`
- `openjiuwen_eval_results_baseline.json`
- `openjiuwen_eval_results_enhanced.json`
- `openjiuwen_eval_report.md`
- `openjiuwen_skill_graph.json`
- `openjiuwen_traces/`

## 代码结构

- `knowledge_agent/openjiuwen_agent`：基于 openJiuwen ReActAgent 的真实主执行链路和工具注册。
- `knowledge_agent/tracing`：统一轨迹 Schema、JSONL 记录与读取。
- `knowledge_agent/skills`：轨迹到技能提炼、技能存储、置信度和证据链。
- `knowledge_agent/graph`：轻量 Skill Graph 构建、检索和 JSON 导出。
- `knowledge_agent/feedback`：基于执行结果的技能置信度更新。
- `knowledge_agent/evaluation`：openJiuwen baseline/enhanced 评测和指标。
- `datasets`：三类模拟场景任务和 seed traces。
- `demos`：openJiuwen ReAct 全流程演示。

## Baseline

Baseline 采用经典 ReAct 无记忆/无技能检索设置：同样使用 openJiuwen `ReActAgent` 和真实 DeepSeek API，但只注册当前领域的业务工具。

Enhanced 在相同任务、相同模型下额外注册 `retrieve_skills`、`record_trace_step`、`update_skill_feedback`、`export_skill_graph`，并将检索到的技能步骤注入 ReAct 工具选择过程。
