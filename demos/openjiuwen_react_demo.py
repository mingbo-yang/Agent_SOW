from __future__ import annotations

import json

from knowledge_agent.openjiuwen_agent.agent import OpenJiuwenKnowledgeAgent


DEMO_TASKS = [
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
    },
]


def main() -> None:
    agent = OpenJiuwenKnowledgeAgent.from_env(max_iterations=10)
    for item in DEMO_TASKS:
        print("=" * 80)
        print(f"Domain: {item['domain']}")
        print(f"Task: {item['task']}")
        baseline = agent.run(item["task"], item["domain"], item, enhanced=False)
        enhanced = agent.run(item["task"], item["domain"], item, enhanced=True)
        print(
            json.dumps(
                {
                    "baseline": {
                        "success": baseline.success,
                        "f1": baseline.key_step_f1,
                        "steps": baseline.plan,
                        "trace_id": baseline.trace.trace_id if baseline.trace else None,
                    },
                    "enhanced": {
                        "success": enhanced.success,
                        "f1": enhanced.key_step_f1,
                        "steps": enhanced.plan,
                        "selected_skills": enhanced.selected_skills,
                        "trace_id": enhanced.trace.trace_id if enhanced.trace else None,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()

