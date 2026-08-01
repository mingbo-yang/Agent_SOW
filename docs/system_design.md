# 系统设计

本项目实现面向企业级 Agent 知识强化的 openJiuwen ReAct 原型。核心目标是把真实 ReAct 工具调用轨迹转化为可复用技能，并通过 Skill Graph 反哺后续任务执行。

## 模块链路

```text
openJiuwen ReActAgent
  -> retrieve_skills / domain tools
  -> TraceRecorder
  -> FeedbackUpdater
  -> SkillStore / SkillGraph
```

## 数据闭环

1. openJiuwen `ReActAgent` 执行任务并调用工具。
2. `TraceRecorder` 记录计划、动作、工具调用、观测、错误和结果。
3. `SkillExtractor` 从成功轨迹提炼可复用步骤，从失败轨迹提炼失败模式和回滚策略。
4. `SkillStore` 保存技能、版本、置信度和 evidence trace id。
5. `SkillGraph` 将技能、工具、领域、失败模式组织成轻量图结构。
6. Enhanced Agent 先调用 `retrieve_skills`，再根据技能步骤和风险提示选择领域工具。
7. `FeedbackUpdater` 根据执行成败更新技能置信度。

## Baseline

Baseline 使用经典 ReAct 设置：openJiuwen `ReActAgent` + DeepSeek API + 当前领域业务工具，不使用技能库、Skill Graph 或知识检索。

Enhanced 使用同一个 ReActAgent 框架和同一批任务，但额外调用知识工具，形成可对比的知识增强实验。

## 评测指标

- 任务成功率
- 关键步骤 F1
- 平均交互轮数
- 平均工具调用次数
- 异常恢复率
- token usage 估算
