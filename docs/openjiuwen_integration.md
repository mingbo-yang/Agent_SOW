# openJiuwenAgent 集成说明

本项目的核心算法模块是独立实现的，便于离线 Demo 和评测；SOW 中要求的 openJiuwenAgent 框架接入通过可选适配层完成。

## 上游框架

openJiuwen Core 仓库：`https://github.com/openJiuwen-ai/agent-core`

其公开 README 中说明 openJiuwen Core 是面向 openJiuwen 框架的大模型应用 Python SDK，提供 Agent 创建、Workflow 编排、LLM 调用、工具调用、高性能运行时、状态恢复和观测能力。

## 本项目如何接入

适配层位于：

```text
knowledge_agent/adapters/openjiuwen.py
```

提供能力：

- `OpenJiuwenRuntimeAdapter.is_available()`：检测当前环境是否安装 openJiuwen。
- `convert_run_to_trace()`：把 openJiuwen/ReAct/Workflow 风格运行事件转换为本项目统一 `Trace`。
- `register_skill_as_openjiuwen_payload()`：把本项目 `SkillSpec` 转成 openJiuwen 技能载荷。
- `make_enhanced_agent()`：基于已提炼技能创建知识增强执行器。

## 安装方式

```bash
pip install -e ".[openjiuwen]"
```

当前机器也可以先检查是否具备 openJiuwen：

```bash
bash scripts/check_openjiuwen.sh
```

## 设计取舍

openJiuwen 依赖较重，并要求 Python 3.11+。因此当前交付不把 openJiuwen 设为强依赖，避免影响两周 MVP 的离线验收。真实部署时建议使用 openJiuwen 负责 Agent runtime、workflow orchestration、tool calling、observability，本项目负责轨迹治理、技能提炼、Skill Graph 和知识增强决策。

