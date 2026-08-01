# Agent SOW

[中文 README](README.zh-CN.md) | English

Agent SOW is an openJiuwen-based knowledge-enhanced Agent prototype for the
Knowledge Reinforcement Agent SOW. The main runtime path is built on
openJiuwen `ReActAgent` and real DeepSeek-compatible API calls.

The project focuses on a reproducible engineering loop:

```text
Task -> openJiuwen ReActAgent -> tools -> trace -> skill extraction
     -> Skill Graph retrieval -> planning augmentation -> feedback update
```

## Highlights

- openJiuwen `ReActAgent` is the primary execution framework.
- DeepSeek API is supported through environment variables, with
  `deepseek-v4-flash` as the default model.
- Baseline, RAG, memory, and enhanced agents share the same openJiuwen runtime.
- Enhanced mode uses Skill Graph retrieval, failure patterns, recovery tools,
  trace recording, and skill confidence updates.
- AI4Science, finance, and industrial/operations tasks are available as
  deterministic local scenarios.
- AgentBench DBBench is integrated as the first public benchmark path.
- Runs generate JSON results, Markdown reports, skill graphs, and execution
  traces.
- API keys, outputs, logs, virtual environments, and external AgentBench source
  are ignored by git.

## Project Status

This is a runnable research prototype, not a production agent platform. It is
designed to show the complete engineering loop and to support fast iteration for
the SOW deliverable.

### Completed

- Core openJiuwen Agent runtime:
  - `OpenJiuwenKnowledgeAgent` creates and executes openJiuwen `ReActAgent`.
  - DeepSeek-compatible API settings are read from environment variables.
  - `agent.invoke()` is the primary execution path.
  - Baseline and enhanced agents use the same runtime and model.

- Knowledge-enhanced execution:
  - Relevant skills are retrieved internally from the Skill Graph before ReAct execution.
  - Enhanced mode uses a gating policy: simple tasks use compact SkillPlan
    hints, fault/recovery tasks expose recovery tools, and DBBench abstains when
    no replay-validated DB skill is available.
  - Retrieved skills are compiled into ordered steps, required tools, failure
    patterns, rollback steps, preconditions, and warnings.
  - Audit-only knowledge tools are not registered by default, avoiding extra
    ReAct turns and tool-choice noise.

- Trace and feedback loop:
  - Execution traces include task metadata, tool calls, observations, errors,
    expected steps, selected skills, recovery flags, and latency.
  - Seed traces can be converted into reusable skills.
  - Skill confidence and evidence trace IDs are updated from execution results.

- Skill Graph:
  - Lightweight in-process graph with JSON export.
  - Supports skill, tool, domain, and failure-mode relationships.
  - Retrieval prioritizes domain match, confidence, context overlap, and failure
    pattern relevance.

- Domain tool coverage:
  - AI4Science tools for literature, variable extraction, validation, protocol
    design, constraint checking, and reporting.
  - Finance tools for claim parsing, policy checking, risk scanning, evidence
    collection, and decisioning.
  - Industrial/operations tools for alarm reading, log inspection, diagnosis,
    runbook selection, health checks, and incident reporting.
  - Recovery tools for context recovery, alternative path selection, rollback,
    and manual escalation.

- Challenge benchmark:
  - `datasets/challenge_tasks.jsonl` includes hard tasks with fault profiles,
    expected recovery steps, constraints, and required ordering.
  - Baseline, RAG, memory, and enhanced modes can be compared on the same task
    set.
  - Metrics include success rate, key-step F1, interactions, tool calls,
    recovery rate, failure detection, rollback usage, required-order rate,
    latency, and estimated token usage.

- Public benchmark integration:
  - AgentBench is cloned externally into `external/AgentBench`.
  - DBBench data is loaded from `external/AgentBench/data/dbbench/`, including
    `dev.jsonl` and larger public files such as `db_out_new.jsonl`.
  - DBBench tasks are adapted into the project task format.
  - DB tools include schema reading, SQL execution, and answer submission.
  - Baseline and enhanced DBBench evaluation outputs are written to
    `outputs/agentbench/`.

- Tests and smoke checks:
  - Unit tests cover tracing, skill extraction/store/graph, openJiuwen tool
    registration, fault/recovery behavior, AgentBench adapter, DB tools, and
    mock AgentBench runner output.
  - DeepSeek smoke test validates real API connectivity.
  - AgentBench DBBench dev smoke has been run with real DeepSeek API.

### Latest Verified Results

The full 100-run study, commands, caveats, and regression analysis are in
[`docs/experiments/scaled_benchmark_100_2026-08-01.md`](docs/experiments/scaled_benchmark_100_2026-08-01.md).

| Evaluation | Baseline | Enhanced | Main result |
| --- | ---: | ---: | --- |
| Simple workflow, 100 repeated runs | 1.000 | 1.000 | Same accuracy; enhanced uses 0.55 fewer tool calls |
| Challenge recovery, 100 repeated runs | 0.000 | 0.680 | Enhanced recovery rate is 1.000 |
| AgentBench DBBench, 100 distinct tasks | 0.920 | 0.890 | No significant difference, exact McNemar `p=0.581` |

The DBBench result is not claimed as an improvement. Generic SQL workflow
skills did not add enough information and previously caused extra tool calls
and premature answers. The final quality gate therefore abstains from DB skill
injection until a DB-specific skill has passed independent replay validation.
The enhanced trace records this decision explicitly.

## Not Yet Completed

- Full AgentBench official runner integration:
  - The current implementation loads AgentBench DBBench dev data and evaluates
    with a local fixture/answer matcher.
  - It does not yet call AgentBench's official server-side result processor as
    the final scorer.

- Full AgentBench environment coverage:
  - Only DBBench is connected.
  - OS, KG, WebShop, ALFWorld, Mind2Web, Avalon, LTP, and card game environments
    are not implemented.

- Full DBBench database backend:
  - Current DB execution uses SQLite fixtures reconstructed from AgentBench task
    records.
  - MySQL/Docker session execution through AgentBench's native DBBench
    environment is not yet wired into the openJiuwen tool adapter.

- Production-grade agent platform features:
  - No multi-tenant permissions, auth, sandbox policy management, release
    rollout, queueing, or distributed execution.
  - No persistent graph database; Skill Graph is intentionally lightweight JSON.
  - No full observability stack beyond JSON traces and reports.

- Broader benchmark rigor:
  - Challenge tasks are useful for controlled recovery demos, but they are
    synthetic.
  - More public benchmark subsets and repeated runs are needed for stable
    statistical claims.

- Token accounting:
  - openJiuwen logs contain model token usage.
  - Evaluation reports still use estimated token usage in some metrics rather
    than a normalized parser over all openJiuwen logs.

- Robust SQL recovery on public DBBench:
  - Recovery tools and SQL failure patterns exist.
  - A dedicated public DBBench recovery subset with injected SQL/tool failures
    has not been finalized.

## Repository Layout

```text
agent-sow/
├── knowledge_agent/
│   ├── openjiuwen_agent/      # openJiuwen ReAct runtime and tools
│   ├── benchmarks/            # AgentBench adapters
│   ├── evaluation/            # evaluation runners and metrics
│   ├── tracing/               # trace schema, recorder, JSONL IO
│   ├── skills/                # skill schema, extractor, persistent store
│   ├── graph/                 # lightweight Skill Graph
│   └── feedback/              # confidence/evidence updates
├── datasets/
│   ├── tasks.jsonl            # simple demo/eval tasks
│   ├── challenge_tasks.jsonl  # hard tasks with faults and recovery steps
│   ├── seed_traces.jsonl      # seed traces for core domains
│   └── agentbench_seed_traces.jsonl
├── demos/
│   └── openjiuwen_react_demo.py
├── scripts/
│   ├── check_openjiuwen.sh
│   ├── test_deepseek_api.py
│   ├── test_openjiuwen_deepseek.sh
│   ├── run_openjiuwen_demo.sh
│   ├── run_openjiuwen_eval.sh
│   ├── setup_agentbench.sh
│   ├── run_agentbench_db_subset.sh
│   └── run_agentbench_db_eval.sh
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.10+
- openJiuwen installed in the active environment
- DeepSeek-compatible API key for real ReAct runs
- Docker for future/native AgentBench environment execution

The current workspace uses `.venv`, but the project does not commit virtual
environment files.

## Installation

```bash
cd /mnt/huawei/ymb/agent-sow
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[openjiuwen,dev]"
```

If openJiuwen has already been installed in `.venv`, you can simply activate or
reuse that environment.

## Environment Variables

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_MODEL="deepseek-v4-flash"
export DEEPSEEK_API_BASE="https://api.deepseek.com"
```

Do not write API keys into source files, scripts, docs, or committed outputs.

## Quick Start

Check openJiuwen:

```bash
bash scripts/check_openjiuwen.sh
```

Run a DeepSeek API smoke test:

```bash
DEEPSEEK_API_KEY=... .venv/bin/python scripts/test_deepseek_api.py
```

Run an openJiuwen smoke test:

```bash
DEEPSEEK_API_KEY=... bash scripts/test_openjiuwen_deepseek.sh
```

Run demos:

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_demo.sh
```

Run baseline vs enhanced evaluation on the default task set:

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh --agent both --limit 3
```

Run all agent modes on the hard challenge set:

```bash
DEEPSEEK_API_KEY=... bash scripts/run_openjiuwen_eval.sh \
  --agent all \
  --dataset datasets/challenge_tasks.jsonl \
  --limit 9
```

## AgentBench DBBench

Clone AgentBench externally:

```bash
bash scripts/setup_agentbench.sh
```

Run a DBBench baseline/enhanced comparison:

```bash
DEEPSEEK_API_KEY=... bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --limit 1 \
  --max-iterations 6
```

Run a known successful public DBBench dev task:

```bash
DEEPSEEK_API_KEY=... bash scripts/run_agentbench_db_eval.sh \
  --agent both \
  --offset 1 \
  --limit 1 \
  --max-iterations 6
```

Outputs are written to:

```text
outputs/agentbench/
├── agentbench_db_results.json
├── agentbench_db_results_baseline.json
├── agentbench_db_results_enhanced.json
├── agentbench_db_report.md
└── traces/
```

## Evaluation Outputs

The standard openJiuwen evaluation writes:

```text
outputs/
├── openjiuwen_eval_results.json
├── openjiuwen_eval_results_baseline.json
├── openjiuwen_eval_results_rag.json
├── openjiuwen_eval_results_memory.json
├── openjiuwen_eval_results_enhanced.json
├── openjiuwen_eval_report.md
├── openjiuwen_skill_graph.json
└── openjiuwen_traces/
```

## Agent Modes

| Mode | Description |
| --- | --- |
| `baseline` | Classic ReAct with domain tools only. No skill retrieval. |
| `rag` | ReAct with static reference documents. No Skill Graph or rollback plan. |
| `memory` | ReAct with raw historical trace summaries. No structured skills. |
| `enhanced` | ReAct with Skill Graph retrieval, structured skill plan, recovery tools, feedback updates, and trace enrichment. |

## Testing

Run the lightweight test suite:

```bash
.venv/bin/python tests/run_tests.py
```

Or use pytest:

```bash
.venv/bin/python -m pytest
```

## Git And Artifact Policy

Ignored by git:

- `.venv/`
- `outputs/`
- `logs/`
- `external/AgentBench/`
- Python caches and build outputs
- API keys and runtime-only logs

AgentBench source is intentionally cloned into `external/AgentBench` and kept
outside version control.

## License

No explicit license has been added yet. Add a `LICENSE` file before publishing
this repository as a public open-source project.
