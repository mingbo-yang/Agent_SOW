# openJiuwenAgent 集成说明

本项目主执行链路基于 openJiuwen `ReActAgent`，并通过 DeepSeek API 进行真实推理和工具选择。

## 上游框架

openJiuwen Core 仓库：`https://github.com/openJiuwen-ai/agent-core`

openJiuwen 负责 Agent runtime、tool calling 和运行日志，本项目负责轨迹治理、技能提炼、Skill Graph 和知识增强决策。

## 主执行链路

```text
knowledge_agent/openjiuwen_agent/
```

该模块创建 openJiuwen `ReActAgent`，将 Skill Graph 检索结果预编译为紧凑 `SkillPlan`，再注册按场景裁剪后的工具集合，并通过 `agent.invoke()` 完成 ReAct 执行。

## 运行方式

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_demo.sh
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh
```

Enhanced ReAct Agent 不再默认把技能检索暴露为 ReAct 工具调用，而是在执行前内部检索 Skill Graph 并注入 SkillPlan hint。普通任务和 DBBench 只注册领域工具；带 `fault_profile` 或 `expected_recovery_steps` 的 hard task 才额外注册恢复工具。Baseline 则只使用领域工具，是无知识检索的经典 ReAct 对照组。
