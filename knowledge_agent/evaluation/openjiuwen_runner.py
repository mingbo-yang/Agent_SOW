from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from knowledge_agent.evaluation.metrics import aggregate_results, compare_reports
from knowledge_agent.evaluation.result import AgentRunResult
from knowledge_agent.openjiuwen_agent.agent import OpenJiuwenKnowledgeAgent


class OpenJiuwenEvaluationRunner:
    AGENT_TYPES = {
        "openjiuwen-react-baseline": "baseline",
        "openjiuwen-react-rag": "rag",
        "openjiuwen-react-memory": "memory",
        "openjiuwen-react-enhanced": "enhanced",
    }

    def __init__(
        self,
        dataset_path: str | Path = "datasets/tasks.jsonl",
        output_dir: str | Path = "outputs",
        limit: int | None = None,
        max_iterations: int = 10,
    ):
        self.dataset_path = Path(dataset_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        self.max_iterations = max_iterations

    def run(self, agent_type: str) -> dict[str, Any]:
        if agent_type not in self.AGENT_TYPES:
            raise ValueError(f"agent_type must be one of {sorted(self.AGENT_TYPES)}")
        mode = self.AGENT_TYPES[agent_type]
        tasks = self._load_tasks()
        agent = OpenJiuwenKnowledgeAgent.from_env(
            skill_store_path=self.output_dir / "openjiuwen_runtime_skills.json",
            trace_dir=self.output_dir / "openjiuwen_traces",
            max_iterations=self.max_iterations,
        )
        results: list[AgentRunResult] = []
        for item in tasks:
            result = self._run_with_retry(agent, item, mode)
            results.append(result)
        result_dicts = [self._result_to_dict(result) for result in results]
        metrics = aggregate_results(results)
        if result_dicts:
            metrics["avg_estimated_token_usage"] = round(
                mean(item["token_usage"]["estimated_total"] for item in result_dicts),
                3,
            )
        else:
            metrics["avg_estimated_token_usage"] = 0.0
        payload = {
            "agent": agent_type,
            "metrics": metrics,
            "results": result_dicts,
        }
        suffix = mode
        (self.output_dir / f"openjiuwen_eval_results_{suffix}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload

    def run_comparison(self) -> dict[str, Any]:
        baseline = self.run("openjiuwen-react-baseline")
        enhanced = self.run("openjiuwen-react-enhanced")
        comparison = {
            "baseline": baseline["metrics"],
            "enhanced": enhanced["metrics"],
            "delta": compare_reports(baseline["metrics"], enhanced["metrics"]),
            "baseline_results": baseline["results"],
            "enhanced_results": enhanced["results"],
        }
        comparison["delta"]["estimated_token_usage_delta"] = round(
            enhanced["metrics"]["avg_estimated_token_usage"]
            - baseline["metrics"]["avg_estimated_token_usage"],
            3,
        )
        (self.output_dir / "openjiuwen_eval_results.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_report(comparison)
        return comparison

    def run_all(self) -> dict[str, Any]:
        reports = {mode: self.run(agent_type) for agent_type, mode in self.AGENT_TYPES.items()}
        comparison = {
            "baseline": reports["baseline"]["metrics"],
            "rag": reports["rag"]["metrics"],
            "memory": reports["memory"]["metrics"],
            "enhanced": reports["enhanced"]["metrics"],
            "delta": compare_reports(reports["baseline"]["metrics"], reports["enhanced"]["metrics"]),
            "baseline_results": reports["baseline"]["results"],
            "rag_results": reports["rag"]["results"],
            "memory_results": reports["memory"]["results"],
            "enhanced_results": reports["enhanced"]["results"],
        }
        comparison["delta"]["estimated_token_usage_delta"] = round(
            reports["enhanced"]["metrics"]["avg_estimated_token_usage"]
            - reports["baseline"]["metrics"]["avg_estimated_token_usage"],
            3,
        )
        (self.output_dir / "openjiuwen_eval_results.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_report(comparison)
        return comparison

    def _run_with_retry(
        self,
        agent: OpenJiuwenKnowledgeAgent,
        item: dict[str, Any],
        mode: str,
    ) -> AgentRunResult:
        last: AgentRunResult | None = None
        for attempt in range(2):
            result = agent.run(item["task"], item["domain"], item, agent_type=mode)
            result.trace.metadata.audit["retry_attempt"] = attempt
            last = result
            if result.success or attempt == 1:
                return result
        return last  # type: ignore[return-value]

    def _load_tasks(self) -> list[dict[str, Any]]:
        tasks = []
        for line in self.dataset_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                tasks.append(json.loads(line))
        if self.limit is not None:
            tasks = self._select_domain_balanced(tasks, self.limit)
        return tasks

    def _select_domain_balanced(self, tasks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_domains: set[str] = set()
        selected_ids: set[str] = set()
        for item in tasks:
            domain = str(item.get("domain", ""))
            task_id = str(item.get("task_id", item.get("task", "")))
            if domain and domain not in seen_domains:
                selected.append(item)
                seen_domains.add(domain)
                selected_ids.add(task_id)
            if len(selected) >= limit:
                return selected
        for item in tasks:
            task_id = str(item.get("task_id", item.get("task", "")))
            if task_id not in selected_ids:
                selected.append(item)
            if len(selected) >= limit:
                return selected
        return selected

    def _result_to_dict(self, result: AgentRunResult) -> dict[str, Any]:
        return {
            "agent": result.agent_type,
            "task_id": result.task_id,
            "task": result.task,
            "domain": result.domain,
            "success": result.success,
            "score": result.score,
            "steps": result.plan,
            "selected_skills": result.selected_skills,
            "interactions": result.interactions,
            "tool_calls": result.tool_calls,
            "key_step_f1": result.key_step_f1,
            "recovered": result.recovered,
            "failure_reason": result.failure_reason,
            "failure_detected": result.failure_detected,
            "matched_failure_patterns": result.matched_failure_patterns,
            "rollback_used": result.rollback_used,
            "recovery_success": result.recovery_success,
            "required_order_ok": result.required_order_ok,
            "latency_ms": result.latency_ms,
            "trace_id": result.trace.trace_id if result.trace else None,
            "trace_path": self._trace_path(result),
            "token_usage": self._estimate_token_usage(result),
        }

    def _trace_path(self, result: AgentRunResult) -> str | None:
        if not result.trace:
            return None
        return str(self.output_dir / "openjiuwen_traces" / result.agent_type / f"{result.trace.trace_id}.json")

    def _estimate_token_usage(self, result: AgentRunResult) -> dict[str, int | str]:
        result_text = result.trace.result.result if result.trace and result.trace.result else ""
        prompt_chars = len(result.task) + sum(len(step) for step in result.plan)
        completion_chars = len(result_text)
        prompt_tokens = max(1, round(prompt_chars / 4))
        completion_tokens = max(1, round(completion_chars / 4))
        return {
            "source": "char_estimate",
            "estimated_prompt_tokens": prompt_tokens,
            "estimated_completion_tokens": completion_tokens,
            "estimated_total": prompt_tokens + completion_tokens,
        }

    def _write_report(self, comparison: dict[str, Any]) -> None:
        lines = [
            "# openJiuwen ReAct Evaluation Report",
            "",
            "| Metric | Baseline | Enhanced | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
        rows = [
            ("success_rate", "success_rate_delta", "Success rate"),
            ("avg_key_step_f1", "key_step_f1_delta", "Key-step F1"),
            ("avg_interactions", "interaction_delta", "Avg interactions"),
            ("avg_tool_calls", "tool_call_delta", "Avg tool calls"),
            ("recovery_rate", "recovery_rate_delta", "Recovery rate"),
            ("failure_detection_rate", "failure_detection_rate_delta", "Failure detection"),
            ("rollback_used_rate", "rollback_used_rate_delta", "Rollback used"),
            ("required_order_rate", "required_order_rate_delta", "Required order"),
            ("avg_latency_ms", "latency_delta", "Avg latency ms"),
            ("avg_estimated_token_usage", "estimated_token_usage_delta", "Estimated token usage"),
        ]
        for metric_key, delta_key, label in rows:
            lines.append(
                f"| {label} | {comparison['baseline'][metric_key]} | "
                f"{comparison['enhanced'][metric_key]} | {comparison['delta'][delta_key]} |"
            )
        lines.extend(
            [
                "",
                "This report is generated by the real openJiuwen ReActAgent path. "
                "DeepSeek participates in planning/tool choice, while local domain tools keep execution deterministic.",
            ]
        )
        (self.output_dir / "openjiuwen_eval_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run openJiuwen ReAct evaluation.")
    parser.add_argument("--agent", choices=["baseline", "rag", "memory", "enhanced", "both", "all"], default="both")
    parser.add_argument("--dataset", default="datasets/tasks.jsonl")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--limit", type=int, default=int(os.getenv("OPENJIUWEN_EVAL_LIMIT", "3")))
    parser.add_argument("--max-iterations", type=int, default=int(os.getenv("OPENJIUWEN_MAX_ITERATIONS", "10")))
    args = parser.parse_args()

    runner = OpenJiuwenEvaluationRunner(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        limit=args.limit,
        max_iterations=args.max_iterations,
    )
    if args.agent == "all":
        result = runner.run_all()
    elif args.agent == "both":
        result = runner.run_comparison()
    elif args.agent == "baseline":
        result = runner.run("openjiuwen-react-baseline")
    elif args.agent == "rag":
        result = runner.run("openjiuwen-react-rag")
    elif args.agent == "memory":
        result = runner.run("openjiuwen-react-memory")
    else:
        result = runner.run("openjiuwen-react-enhanced")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
