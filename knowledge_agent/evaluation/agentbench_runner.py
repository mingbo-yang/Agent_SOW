from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from knowledge_agent.benchmarks.agentbench_adapter import AgentBenchDBAdapter
from knowledge_agent.evaluation.result import AgentRunResult
from knowledge_agent.openjiuwen_agent.agent import OpenJiuwenKnowledgeAgent


class AgentBenchEvaluationRunner:
    AGENT_TYPES = {
        "baseline": "baseline",
        "rag": "rag",
        "memory": "memory",
        "enhanced": "enhanced",
    }

    def __init__(
        self,
        benchmark: str = "dbbench",
        split: str = "dev",
        output_dir: str | Path = "outputs/agentbench",
        agentbench_root: str | Path = "external/AgentBench",
        limit: int = 3,
        offset: int = 0,
        max_iterations: int = 10,
    ):
        if benchmark != "dbbench":
            raise ValueError("Only AgentBench DBBench is supported in this engineering pass.")
        self.benchmark = benchmark
        self.split = split
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "traces").mkdir(parents=True, exist_ok=True)
        self.adapter = AgentBenchDBAdapter(agentbench_root=agentbench_root, split=split)
        self.limit = limit
        self.offset = offset
        self.max_iterations = max_iterations

    def run(self, agent: str) -> dict[str, Any]:
        if agent not in self.AGENT_TYPES:
            raise ValueError(f"agent must be one of {sorted(self.AGENT_TYPES)}")
        mode = self.AGENT_TYPES[agent]
        tasks = self.adapter.load_tasks(limit=self.limit, offset=self.offset)
        openjiuwen_agent = OpenJiuwenKnowledgeAgent.from_env(
            skill_store_path=self.output_dir / f"agentbench_runtime_skills_{mode}.json",
            trace_dir=self.output_dir / "traces",
            seed_trace_path="datasets/agentbench_seed_traces.jsonl",
            max_iterations=self.max_iterations,
        )
        results = []
        for task in tasks:
            result = self._run_one(openjiuwen_agent, task, mode)
            results.append(result)
        metrics = self._metrics(results)
        payload = {
            "benchmark": "AgentBench",
            "environment": self.benchmark,
            "split": self.split,
            "agent": mode,
            "metrics": metrics,
            "results": results,
        }
        (self.output_dir / f"agentbench_db_results_{mode}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload

    def run_comparison(self) -> dict[str, Any]:
        baseline = self.run("baseline")
        enhanced = self.run("enhanced")
        comparison = {
            "benchmark": "AgentBench",
            "environment": self.benchmark,
            "split": self.split,
            "baseline": baseline["metrics"],
            "enhanced": enhanced["metrics"],
            "baseline_results": baseline["results"],
            "enhanced_results": enhanced["results"],
            "delta": {
                "official_success_rate_delta": round(
                    enhanced["metrics"]["official_success_rate"] - baseline["metrics"]["official_success_rate"], 3
                ),
                "task_success_rate_delta": round(
                    enhanced["metrics"]["task_success_rate"] - baseline["metrics"]["task_success_rate"], 3
                ),
                "sql_error_recovery_rate_delta": round(
                    enhanced["metrics"]["sql_error_recovery_rate"] - baseline["metrics"]["sql_error_recovery_rate"], 3
                ),
            },
        }
        (self.output_dir / "agentbench_db_results.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_report(comparison)
        return comparison

    def run_all(self) -> dict[str, Any]:
        reports = {agent: self.run(agent) for agent in self.AGENT_TYPES}
        payload = {
            "benchmark": "AgentBench",
            "environment": self.benchmark,
            "split": self.split,
            "metrics": {agent: report["metrics"] for agent, report in reports.items()},
            "results": {agent: report["results"] for agent, report in reports.items()},
        }
        (self.output_dir / "agentbench_db_results.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload

    def _run_one(self, agent: OpenJiuwenKnowledgeAgent, task: dict[str, Any], mode: str) -> dict[str, Any]:
        result = agent.run(task["task"], task["domain"], task, agent_type=mode)
        final_answer = self.adapter.to_agentbench_answer(result)
        score = self.adapter.official_score(task, final_answer)
        official_success = score["official_success"]
        success = result.success and (bool(official_success) if official_success is not None else True)
        return self._result_to_dict(result, task, final_answer, score, success)

    def _result_to_dict(
        self,
        result: AgentRunResult,
        task: dict[str, Any],
        final_answer: str,
        official_score: dict[str, Any],
        success: bool,
    ) -> dict[str, Any]:
        metadata = task.get("benchmark_metadata") or {}
        trace_path = None
        if result.trace:
            trace_path = str(self.output_dir / "traces" / result.agent_type / f"{result.trace.trace_id}.json")
        return {
            "benchmark": "AgentBench",
            "environment": "dbbench",
            "split": self.split,
            "official_task_id": metadata.get("official_task_id") or task.get("task_id"),
            "task_id": task.get("task_id"),
            "agent": result.agent_type,
            "success": success,
            "task_success": result.success,
            "official_score": official_score["official_score"],
            "official_success": official_score["official_success"],
            "official_available": official_score["official_available"],
            "scorer": official_score["scorer"],
            "final_answer": final_answer,
            "failure_reason": result.failure_reason,
            "trace_path": trace_path,
            "selected_skills": result.selected_skills,
            "tool_calls": result.tool_calls,
            "turns": result.interactions,
            "steps": result.plan,
            "key_step_f1": result.key_step_f1,
            "recovery_success": result.recovery_success,
            "matched_failure_patterns": result.matched_failure_patterns,
            "latency_ms": result.latency_ms,
            "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
            "benchmark_metadata": metadata,
        }

    def _metrics(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        if not results:
            return {
                "official_success_rate": 0.0,
                "task_success_rate": 0.0,
                "avg_turns": 0.0,
                "avg_tool_calls": 0.0,
                "sql_error_recovery_rate": 0.0,
                "avg_latency_ms": 0.0,
            }
        official_scored = [item for item in results if item["official_success"] is not None]
        recoverable = [item for item in results if any("SQL" in pattern for pattern in item["matched_failure_patterns"])]
        return {
            "official_success_rate": _rate(official_scored, "official_success"),
            "task_success_rate": _rate(results, "task_success"),
            "avg_turns": round(mean(item["turns"] for item in results), 3),
            "avg_tool_calls": round(mean(item["tool_calls"] for item in results), 3),
            "sql_error_recovery_rate": _rate(recoverable, "recovery_success") if recoverable else 0.0,
            "avg_latency_ms": round(mean(item["latency_ms"] for item in results), 3),
        }

    def _write_report(self, comparison: dict[str, Any]) -> None:
        lines = [
            "# AgentBench DBBench Evaluation",
            "",
            "| Metric | Baseline | Enhanced | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
        rows = [
            ("official_success_rate", "official_success_rate_delta", "Official success rate"),
            ("task_success_rate", "task_success_rate_delta", "Task success rate"),
            ("sql_error_recovery_rate", "sql_error_recovery_rate_delta", "SQL recovery rate"),
            ("avg_turns", None, "Avg turns"),
            ("avg_tool_calls", None, "Avg tool calls"),
            ("avg_latency_ms", None, "Avg latency ms"),
        ]
        for metric, delta, label in rows:
            delta_value = comparison["delta"].get(delta, "") if delta else ""
            lines.append(
                f"| {label} | {comparison['baseline'][metric]} | {comparison['enhanced'][metric]} | {delta_value} |"
            )
        lines.extend(
            [
                "",
                "Generated by the openJiuwen ReActAgent path with DBBench domain tools.",
            ]
        )
        (self.output_dir / "agentbench_db_report.md").write_text("\n".join(lines), encoding="utf-8")


def _rate(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0
    return round(sum(1 for item in items if item.get(key)) / len(items), 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AgentBench DBBench subset through openJiuwen ReAct.")
    parser.add_argument("--benchmark", choices=["dbbench"], default="dbbench")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=int(os.getenv("AGENTBENCH_LIMIT", "3")))
    parser.add_argument("--offset", type=int, default=int(os.getenv("AGENTBENCH_OFFSET", "0")))
    parser.add_argument("--agent", choices=["baseline", "rag", "memory", "enhanced", "both", "all"], default="both")
    parser.add_argument("--output-dir", default="outputs/agentbench")
    parser.add_argument("--agentbench-root", default="external/AgentBench")
    parser.add_argument("--max-iterations", type=int, default=int(os.getenv("OPENJIUWEN_MAX_ITERATIONS", "10")))
    args = parser.parse_args()

    runner = AgentBenchEvaluationRunner(
        benchmark=args.benchmark,
        split=args.split,
        output_dir=args.output_dir,
        agentbench_root=args.agentbench_root,
        limit=args.limit,
        offset=args.offset,
        max_iterations=args.max_iterations,
    )
    if args.agent == "both":
        result = runner.run_comparison()
    elif args.agent == "all":
        result = runner.run_all()
    else:
        result = runner.run(args.agent)
        (runner.output_dir / "agentbench_db_results.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        runner._write_report(
            {
                "baseline": result["metrics"],
                "enhanced": result["metrics"],
                "delta": {
                    "official_success_rate_delta": 0.0,
                    "task_success_rate_delta": 0.0,
                    "sql_error_recovery_rate_delta": 0.0,
                },
            }
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
