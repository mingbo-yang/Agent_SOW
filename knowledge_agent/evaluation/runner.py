from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from knowledge_agent.evaluation.metrics import aggregate_results, compare_reports
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.agent import AgentRunResult, BaselineAgent, KnowledgeEnhancedAgent
from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import load_traces_jsonl


class EvaluationRunner:
    def __init__(
        self,
        dataset_path: str | Path = "datasets/tasks.jsonl",
        seed_trace_path: str | Path = "datasets/seed_traces.jsonl",
        output_dir: str | Path = "outputs",
    ):
        self.dataset_path = Path(dataset_path)
        self.seed_trace_path = Path(seed_trace_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, agent_type: str, dataset_path: str | Path | None = None) -> dict[str, Any]:
        tasks = self._load_tasks(Path(dataset_path) if dataset_path else self.dataset_path)
        results = self._run_tasks(agent_type, tasks)
        report = aggregate_results(results)
        payload = {
            "agent": agent_type,
            "metrics": report,
            "results": [self._result_to_dict(result) for result in results],
        }
        self._write_outputs(agent_type, payload)
        return payload

    def run_comparison(self) -> dict[str, Any]:
        baseline = self.run("baseline")
        enhanced = self.run("enhanced")
        comparison = {
            "baseline": baseline["metrics"],
            "enhanced": enhanced["metrics"],
            "delta": compare_reports(baseline["metrics"], enhanced["metrics"]),
        }
        (self.output_dir / "eval_comparison.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_markdown_report(comparison)
        return comparison

    def _run_tasks(self, agent_type: str, tasks: list[dict[str, Any]]) -> list[AgentRunResult]:
        if agent_type == "baseline":
            agent = BaselineAgent(trace_dir=self.output_dir / "traces" / "baseline")
            return [agent.run(item["task"], item["domain"], item) for item in tasks]

        if agent_type != "enhanced":
            raise ValueError("agent_type must be 'baseline' or 'enhanced'")

        store = self._bootstrap_skill_store()
        graph = SkillGraph.build_from_skills(store.list())
        agent = KnowledgeEnhancedAgent(
            skill_graph=graph,
            skill_store=store,
            trace_dir=self.output_dir / "traces" / "enhanced",
        )
        results = []
        for item in tasks:
            result = agent.run(item["task"], item["domain"], item)
            results.append(result)
            graph = SkillGraph.build_from_skills(store.list())
            agent.skill_graph = graph
        graph.export_json(self.output_dir / "skill_graph.json")
        return results

    def _bootstrap_skill_store(self) -> SkillStore:
        store = SkillStore(self.output_dir / "runtime_skills.json")
        traces = load_traces_jsonl(self.seed_trace_path)
        skills = SkillExtractor(use_llm=False).extract_from_traces(traces)
        store.save_many(skills)
        return store

    def _load_tasks(self, path: Path) -> list[dict[str, Any]]:
        tasks = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                tasks.append(json.loads(line))
        return tasks

    def _write_outputs(self, agent_type: str, payload: dict[str, Any]) -> None:
        path = self.output_dir / f"eval_results_{agent_type}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_markdown_report(self, comparison: dict[str, Any]) -> None:
        lines = [
            "# Knowledge Agent Evaluation Report",
            "",
            "| Metric | Baseline | Enhanced | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
        labels = {
            "success_rate": "Success rate",
            "avg_key_step_f1": "Key-step F1",
            "avg_interactions": "Avg interactions",
            "avg_tool_calls": "Avg tool calls",
            "recovery_rate": "Recovery rate",
        }
        for key, label in labels.items():
            delta_key = {
                "success_rate": "success_rate_delta",
                "avg_key_step_f1": "key_step_f1_delta",
                "avg_interactions": "interaction_delta",
                "avg_tool_calls": "tool_call_delta",
                "recovery_rate": "recovery_rate_delta",
            }[key]
            lines.append(
                f"| {label} | {comparison['baseline'][key]} | "
                f"{comparison['enhanced'][key]} | {comparison['delta'][delta_key]} |"
            )
        lines.extend(
            [
                "",
                "Enhanced mode bootstraps skills from seed trajectories, retrieves them through a lightweight Skill Graph, injects steps/failure recovery into planning, and updates skill confidence after every run.",
            ]
        )
        (self.output_dir / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")

    def _result_to_dict(self, result: AgentRunResult) -> dict[str, Any]:
        return {
            "task": result.task,
            "domain": result.domain,
            "success": result.success,
            "score": result.score,
            "plan": result.plan,
            "selected_skills": result.selected_skills,
            "interactions": result.interactions,
            "tool_calls": result.tool_calls,
            "key_step_f1": result.key_step_f1,
            "recovered": result.recovered,
            "failure_reason": result.failure_reason,
            "trace_id": result.trace.trace_id if result.trace else None,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Knowledge Agent evaluation.")
    parser.add_argument("--agent", choices=["baseline", "enhanced", "both"], default="both")
    parser.add_argument("--dataset", default="datasets/tasks.jsonl")
    parser.add_argument("--seed-traces", default="datasets/seed_traces.jsonl")
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()

    runner = EvaluationRunner(args.dataset, args.seed_traces, args.output_dir)
    if args.agent == "both":
        report = runner.run_comparison()
    else:
        report = runner.run(args.agent)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

