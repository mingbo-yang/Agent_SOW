# Demo Guide

运行全部 Demo：

```bash
bash scripts/run_demo.sh
```

运行单个 Demo：

```bash
python -m demos.ai4science_demo
python -m demos.finance_demo
python -m demos.industrial_demo
```

每个 Demo 都会输出 baseline 和 enhanced 的计划与成功状态。Enhanced 版本会先从 seed traces 中提炼技能，再通过 Skill Graph 检索相关技能补全规划。

