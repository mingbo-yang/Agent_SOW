from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowledge_agent.skills.schema import SkillSpec


@dataclass
class CheckResult:
    ok: bool
    missing_steps: list[str] = field(default_factory=list)
    unavailable_tools: list[str] = field(default_factory=list)
    known_risks: list[str] = field(default_factory=list)


class ExecutionChecker:
    """Lightweight executable-plan checker for the MVP evaluator."""

    def __init__(self, available_tools: set[str]):
        self.available_tools = available_tools

    def check(
        self,
        plan: list[str],
        expected_steps: list[str],
        selected_skills: list[SkillSpec] | None = None,
        context: dict[str, Any] | None = None,
    ) -> CheckResult:
        selected_skills = selected_skills or []
        missing = [step for step in expected_steps if step not in plan]
        tool_names = [self.tool_for_step(step) for step in plan]
        unavailable = [tool for tool in tool_names if tool and tool not in self.available_tools]
        risks = []
        text = f"{context or {}}".lower()
        for skill in selected_skills:
            for pattern in skill.failure_patterns:
                if pattern.lower() in text:
                    risks.append(pattern)
        return CheckResult(
            ok=not missing and not unavailable,
            missing_steps=missing,
            unavailable_tools=unavailable,
            known_risks=risks,
        )

    def tool_for_step(self, step: str) -> str:
        mapping = {
            "collect_literature": "literature_search",
            "extract_variables": "paper_reader",
            "validate_inputs": "schema_validator",
            "design_protocol": "protocol_designer",
            "verify_constraints": "constraint_checker",
            "generate_report": "report_writer",
            "extract_claim": "document_parser",
            "check_policy": "policy_checker",
            "anomaly_check": "risk_scanner",
            "collect_evidence": "evidence_collector",
            "approve_or_reject": "decision_engine",
            "read_alarm": "monitoring_reader",
            "inspect_logs": "log_search",
            "root_cause_analysis": "diagnosis_engine",
            "select_recovery": "runbook_selector",
            "verify_recovery": "health_checker",
            "write_incident": "report_writer",
            "select_alternative_tool": "tool_router",
            "retry_with_constraints": "constraint_checker",
            "manual_review": "human_review",
            "ask_for_more_context": "human_review",
            "retry_tool": "tool_router",
        }
        return mapping.get(step, step)

