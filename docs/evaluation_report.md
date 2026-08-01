# 评测报告

当前 MVP 使用 `datasets/tasks.jsonl` 中的 9 条可控任务进行 baseline/enhanced 对比，覆盖 AI4Science、金融、工业/运维三类场景。

## 最新运行结果

| Metric | Baseline | Enhanced | Delta |
| --- | ---: | ---: | ---: |
| Success rate | 0.0 | 1.0 | +1.0 |
| Key-step F1 | 0.44 | 1.0 | +0.56 |
| Avg interactions | 8.0 | 5.667 | -2.333 |
| Avg tool calls | 8.0 | 5.667 | -2.333 |
| Recovery rate | 0.0 | 0.0 | 0.0 |

## 复现命令

```bash
bash scripts/run_eval.sh
```

运行后会更新：

- `outputs/eval_results_baseline.json`
- `outputs/eval_results_enhanced.json`
- `outputs/eval_comparison.json`
- `outputs/eval_report.md`
- `outputs/skill_graph.json`
- `outputs/runtime_skills.json`

