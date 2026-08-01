# 系统设计

本项目实现面向企业级 Agent 知识强化的独立 MVP，核心目标是把 Agent 运行轨迹转化为可复用技能，并通过 Skill Graph 反哺后续规划决策。

本项目不把 openJiuwen 作为强依赖，但提供可选适配层，使 openJiuwen Agent/Core 的运行轨迹能够进入同一套知识强化闭环。

## 模块链路

```text
TraceRecorder -> SkillExtractor -> SkillStore -> SkillGraph -> KnowledgeEnhancedAgent -> FeedbackUpdater
```

openJiuwen 接入路径：

```text
openJiuwen ReAct/Workflow run events -> OpenJiuwenRuntimeAdapter -> Trace -> SkillExtractor -> SkillGraph
```

## 数据闭环

1. Agent 执行任务时，`TraceRecorder` 记录计划、动作、工具调用、观测、错误和结果。
2. `SkillExtractor` 从成功轨迹提炼可复用步骤，从失败轨迹提炼失败模式和回滚策略。
3. `SkillStore` 保存技能、版本、置信度和 evidence trace id。
4. `SkillGraph` 将技能、工具、领域、失败模式组织成轻量图结构。
5. `KnowledgeEnhancedAgent` 在执行前检索相关技能，把步骤、约束和回滚策略注入规划。
6. `FeedbackUpdater` 根据线上执行成败更新技能置信度。

## 评测指标

- 任务成功率
- 关键步骤 F1
- 平均交互轮数
- 平均工具调用次数
- 异常恢复率
