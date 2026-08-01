# 技术报告

## 轨迹统一表示

轨迹被表示为 `Trace(task, domain, steps, result, metadata)`。每个 `TraceStep` 绑定状态、计划、动作、工具调用、观测和 reward，便于后续回放、审计和技能提炼。

## 技能化知识加工

`SkillExtractor` 默认使用离线规则：

- 成功轨迹提供稳定步骤、工具链和输入输出。
- 失败轨迹提供 failure pattern。
- 同域、同工具链、触发词相近的技能会被合并。
- 技能置信度由成功率、证据数量和恢复证据共同决定。

## Skill Graph

图中包含 skill、tool、domain、failure mode 节点，并用 `uses_tool`、`belongs_to`、`handles_failure`、`alternative_to`、`conflicts_with` 表示关系。运行时按领域、关键词、置信度和失败模式召回技能。

## 决策增强

`KnowledgeEnhancedAgent` 将检索到的技能步骤注入 baseline plan，并执行可执行性检查。任务结束后，使用技能的成功会提升置信度，失败会降低置信度并记录失败模式。

