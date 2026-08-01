# 100-Run Benchmark and Negative-Optimization Study

Date: 2026-08-01

## Scope

All runs used the real openJiuwen `ReActAgent` path and the real DeepSeek API
with `deepseek-v4-flash`. API credentials were supplied only through the
process environment. Generated results and traces are under
`outputs/scaled_validation/` and are intentionally ignored by git.

Three evaluations were scaled to 100 agent-task runs per mode:

| Evaluation | Samples | Sampling |
| --- | ---: | --- |
| Simple workflow | 100 | Stability run repeating 9 deterministic local tasks |
| Challenge recovery | 100 | Stability run repeating 9 fault-injected local tasks |
| AgentBench DBBench | 100 | 100 distinct executable tasks from `db_out_new` |

The local 100-run evaluations are repeated trials, not 100 independent task
definitions. DBBench is the public benchmark result.

## Final Results

### Simple workflow stability

| Agent | Success | Key-step F1 | Tool calls | Latency ms | Estimated tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1.000 | 1.000 | 7.020 | 17621.670 | 448.170 |
| Enhanced | 1.000 | 1.000 | 6.470 | 16545.180 | 415.710 |
| Delta | 0.000 | 0.000 | -0.550 | -1076.490 | -32.460 |

The lightweight SkillPlan path preserved accuracy while reducing interactions,
latency, and estimated token use.

### Challenge recovery stability

| Agent | Success | Key-step F1 | Recovery | Required order | Tool calls | Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.000 | 0.901 | 0.000 | 0.510 | 8.300 | 21526.100 |
| Enhanced | 0.680 | 0.957 | 1.000 | 0.710 | 6.810 | 16422.450 |
| Delta | +0.680 | +0.056 | +1.000 | +0.200 | -1.490 | -5103.650 |

Enhanced success by domain was 0.528 for AI4Science, 0.917 for finance, and
0.571 for industrial/operations. Recovery succeeded in every enhanced run that
encountered the injected fault. The four parallel 25-run workers produced a
36/36/28 domain split, so the aggregate is a stability result rather than a
strictly balanced domain estimate.

### AgentBench DBBench

The baseline and final knowledge-gated enhanced runs used the same 100 distinct
executable tasks and `max_iterations=4`.

| Agent | Official success | Task-chain success | Tool calls | Latency ms | Selected skills |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.920 | 1.000 | 7.380 | 8046.940 | 0/100 |
| Enhanced, final gate | 0.890 | 1.000 | 7.460 | 8123.140 | 0/100 |

Paired outcomes were: 84 both correct, 3 both wrong, 8 baseline-only, and 5
enhanced-only. An exact McNemar test gives `p=0.581`; the observed three-point
difference is not statistically significant at this sample size. The 95%
Wilson intervals also overlap: baseline `[0.850, 0.959]`, enhanced
`[0.814, 0.937]`.

This is parity, not a positive DBBench gain. The final enhanced policy abstains
from injecting the generic DB skill because it has not passed independent
replay validation. The trace records `knowledge_mode=off`,
`knowledge_abstained=true`, and `no_replay_validated_db_skill`.

## What Caused the Regression

The logs exposed four separate causes:

1. Skill retrieval and audit tools consumed ReAct iterations without adding SQL
   knowledge.
2. Registering 11 tools instead of the three DB tools increased tool-selection
   noise.
3. A generic workflow skill encouraged early submission but did not improve
   schema linking, filtering, projection, aggregation, or ordering.
4. The model sometimes shortened an exact single-cell database value before
   submission, for example `Mike Dunleavy (27)` to `Mike Dunleavy`.

## Implemented Fixes

- Skill retrieval is compiled before ReAct instead of consuming a model tool
  call.
- Tool exposure is gated: recovery tools are available only for actual fault
  tasks, and DBBench keeps only schema, SQL, and submission tools.
- DB results are auto-finalized when the model has a valid SQL result but uses
  all iterations before submission.
- Single-column scalar values preserve the exact database value when the model
  submits a truncated substring. This rule does not inspect the gold answer.
- DB SkillPlan injection now abstains by default until a replay-validated,
  DB-specific skill exists. Explicit experiments can opt in with
  `enable_db_skill_plan=true`.
- Local evaluation supports `--repeat-to-limit` for reproducible 100-run
  stability tests with unique trace task IDs.

The exact scalar regression was replayed with the original failing task and
changed its score from incorrect to correct. The final abstention policy also
passed a real-API 3-task smoke test with 3/3 correct and audit metadata present.

## Remaining Engineering Work

- Build DB-specific skills for schema linking, SQL pattern selection, and query
  repair, then validate them on held-out trace replay before enabling them.
- Freeze skill updates during benchmark evaluation to maintain a strict
  train/evaluation boundary.
- Add first-class process sharding to the runner instead of merging worker
  outputs externally.
- Parse exact token usage from openJiuwen logs rather than estimating it for
  local evaluations.
- Connect AgentBench's native DB service and official result processor; current
  DB execution uses executable SQLite fixtures reconstructed from public task
  records.

## Reproduction

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
.venv/bin/python -m knowledge_agent.evaluation.openjiuwen_runner \
  --agent both --dataset datasets/tasks.jsonl \
  --output-dir outputs/scaled_validation/simple_100 \
  --limit 100 --repeat-to-limit --max-iterations 6
```

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
.venv/bin/python -m knowledge_agent.evaluation.openjiuwen_runner \
  --agent both --dataset datasets/challenge_tasks.jsonl \
  --output-dir outputs/scaled_validation/challenge_100 \
  --limit 100 --repeat-to-limit --max-iterations 6
```

```bash
DEEPSEEK_MODEL=deepseek-v4-flash \
bash scripts/run_agentbench_db_eval.sh \
  --agent both --split db_out_new --limit 100 \
  --require-executable-fixture --max-iterations 4
```
