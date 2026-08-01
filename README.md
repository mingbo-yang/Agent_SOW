# 知识强化 Agent MVP

这是一个独立可运行的知识强化 Agent 原型，位于 `zju_agent` 目录内。它实现了 SOW 代码部分的最小闭环，并提供 openJiuwenAgent 可选适配层：

```text
任务输入 -> 轨迹记录 -> 技能提炼 -> Skill Graph -> 技能检索增强规划 -> 执行反馈 -> 技能更新
```

## 快速运行

```bash
bash scripts/run_demo.sh
bash scripts/run_eval.sh
python3 tests/run_tests.py
bash scripts/check_openjiuwen.sh
```

评测输出位于 `outputs/`：

- `eval_results_baseline.json`
- `eval_results_enhanced.json`
- `eval_comparison.json`
- `eval_report.md`
- `skill_graph.json`
- `runtime_skills.json`
- `traces/`

## 代码结构

- `knowledge_agent/tracing`：统一轨迹 Schema、JSONL 记录与读取。
- `knowledge_agent/skills`：轨迹到技能提炼、技能存储、置信度和证据链。
- `knowledge_agent/graph`：轻量 Skill Graph 构建、检索和 JSON 导出。
- `knowledge_agent/planner`：Baseline Agent、Knowledge Enhanced Agent、执行检查器。
- `knowledge_agent/feedback`：基于执行结果的技能置信度更新。
- `knowledge_agent/evaluation`：任务成功率、关键步骤 F1、交互轮数、工具调用次数等评测。
- `datasets`：三类模拟场景任务和 seed traces。
- `demos`：AI4Science、金融、工业/运维演示。

## 设计说明

当前版本不绑定任何特定 Agent 框架，也不要求外部 LLM API。技能提炼默认走规则版，保证离线可复现；后续可在 `SkillExtractor.extract_with_llm()` 中接入 LLM 结构化提炼。

SOW 中“基于 openJiuwenAgent 框架”的部分通过 `knowledge_agent/adapters/openjiuwen.py` 对齐。安装 openJiuwen 后，可将 openJiuwen 的运行事件转换为本项目统一 Trace，并将提炼出的 SkillSpec 注册为 openJiuwen 可消费的技能载荷。详见 `docs/openjiuwen_integration.md`。
