# openJiuwenAgent 集成说明

本项目主执行链路基于 openJiuwen `ReActAgent`，并通过 DeepSeek API 进行真实推理和工具选择。

## 上游框架

openJiuwen Core 仓库：`https://github.com/openJiuwen-ai/agent-core`

openJiuwen 负责 Agent runtime、tool calling 和运行日志，本项目负责轨迹治理、技能提炼、Skill Graph 和知识增强决策。

## 主执行链路

```text
knowledge_agent/openjiuwen_agent/
```

该模块创建 openJiuwen `ReActAgent`，注册知识工具和领域工具，并通过 `agent.invoke()` 完成 ReAct 执行。

## 运行方式

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_demo.sh
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh
```

Enhanced ReAct Agent 会先调用 `retrieve_skills`，再根据 Skill Graph 返回的步骤调用 AI4Science、金融、工业/运维领域工具。Baseline 则只使用领域工具，是无知识检索的经典 ReAct 对照组。
