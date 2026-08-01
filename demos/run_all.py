from __future__ import annotations

from pathlib import Path

from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.agent import BaselineAgent, KnowledgeEnhancedAgent
from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import load_traces_jsonl


TASKS = [
    {
        "domain": "ai4science",
        "task": "Design a reproducible CRISPR screening experiment from recent papers and constraints.",
        "expected_steps": [
            "collect_literature",
            "extract_variables",
            "validate_inputs",
            "design_protocol",
            "verify_constraints",
            "generate_report",
        ],
        "required_before_report": ["verify_constraints"],
    },
    {
        "domain": "finance",
        "task": "Review reimbursement with policy limits and suspicious duplicate receipts.",
        "expected_steps": [
            "extract_claim",
            "check_policy",
            "anomaly_check",
            "collect_evidence",
            "approve_or_reject",
        ],
        "required_before_report": [],
    },
    {
        "domain": "industrial",
        "task": "Diagnose a production service alarm with high latency and recent deployment.",
        "expected_steps": [
            "read_alarm",
            "inspect_logs",
            "root_cause_analysis",
            "select_recovery",
            "verify_recovery",
            "write_incident",
        ],
        "required_before_report": ["verify_recovery"],
    },
]


def build_graph(output_dir: Path) -> tuple[SkillStore, SkillGraph]:
    store = SkillStore(output_dir / "demo_skills.json")
    traces = load_traces_jsonl("datasets/seed_traces.jsonl")
    store.save_many(SkillExtractor().extract_from_traces(traces))
    graph = SkillGraph.build_from_skills(store.list())
    graph.export_json(output_dir / "demo_skill_graph.json")
    return store, graph


def main() -> None:
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    store, graph = build_graph(output_dir)
    baseline = BaselineAgent(trace_dir=output_dir / "traces" / "demo_baseline")
    enhanced = KnowledgeEnhancedAgent(
        graph,
        skill_store=store,
        trace_dir=output_dir / "traces" / "demo_enhanced",
    )

    for item in TASKS:
        print("=" * 80)
        print(f"Domain: {item['domain']}")
        print(f"Task: {item['task']}")
        base = baseline.run(item["task"], item["domain"], item)
        rich = enhanced.run(item["task"], item["domain"], item)
        print(f"Baseline: success={base.success}, f1={base.key_step_f1}, steps={base.plan}")
        print(
            "Enhanced: "
            f"success={rich.success}, f1={rich.key_step_f1}, "
            f"skills={len(rich.selected_skills)}, steps={rich.plan}"
        )
    print("=" * 80)
    print("Artifacts written to outputs/: demo_skills.json, demo_skill_graph.json, traces/")


if __name__ == "__main__":
    main()

