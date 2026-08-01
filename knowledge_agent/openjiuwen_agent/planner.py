from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from knowledge_agent.skills.schema import SkillSpec


ERROR_RECOVERY_ACTIONS = {
    "MISSING_METADATA": "recover_context",
    "BIO_SAFETY_CONFLICT": "manual_escalation",
    "VARIABLE_MISMATCH": "recover_context",
    "POLICY_EVIDENCE_REQUIRED": "recover_context",
    "DUPLICATE_RECEIPT_EVIDENCE": "recover_context",
    "POLICY_VERSION_CHANGED": "recover_context",
    "LOG_TOOL_UNAVAILABLE": "select_alternative_path",
    "RECENT_DEPLOYMENT_REGRESSION": "execute_rollback",
    "HEALTH_CHECK_FAILED": "execute_rollback",
    "RUNBOOK_NOT_APPLICABLE": "select_alternative_path",
}


@dataclass
class SkillPlan:
    ordered_steps: list[str] = field(default_factory=list)
    failure_patterns: list[str] = field(default_factory=list)
    rollback_steps: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    known_constraints: list[str] = field(default_factory=list)
    matched_failure_patterns: list[str] = field(default_factory=list)
    plan_warnings: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_skill_plan(skills: list[SkillSpec], context: dict[str, Any]) -> SkillPlan:
    plan = SkillPlan()
    for skill in skills:
        plan.ordered_steps = _merge(plan.ordered_steps, skill.steps)
        plan.failure_patterns = _merge(plan.failure_patterns, skill.failure_patterns)
        plan.rollback_steps = _merge(plan.rollback_steps, skill.rollback)
        plan.preconditions = _merge(plan.preconditions, skill.preconditions)
        plan.required_tools = _merge(plan.required_tools, skill.tools)

    constraints = context.get("constraints") or []
    if isinstance(constraints, dict):
        constraints = [f"{key}:{value}" for key, value in constraints.items()]
    plan.known_constraints = [str(item) for item in constraints]

    fault_terms = _fault_terms(context)
    for pattern in plan.failure_patterns:
        if _tokens(pattern) & fault_terms:
            plan.matched_failure_patterns.append(pattern)
    for error_code in _fault_error_codes(context):
        recovery = ERROR_RECOVERY_ACTIONS.get(error_code)
        if recovery and recovery not in plan.rollback_steps:
            plan.rollback_steps.append(recovery)
        if error_code and error_code not in plan.matched_failure_patterns:
            plan.matched_failure_patterns.append(error_code)

    for precondition in plan.preconditions:
        if precondition.endswith("_available") and precondition not in json.dumps(context, ensure_ascii=False):
            plan.plan_warnings.append(f"precondition_check:{precondition}")
    if context.get("fault_profile") and not plan.rollback_steps:
        plan.blocked_reasons.append("fault_profile_present_without_recovery")
    return plan


def _merge(left: list[str], right: list[str]) -> list[str]:
    result = list(left)
    for item in right:
        if item not in result:
            result.append(item)
    return result


def _fault_error_codes(context: dict[str, Any]) -> list[str]:
    profile = context.get("fault_profile") or {}
    failures = profile.get("failures") or []
    if not failures and profile.get("error_code"):
        failures = [profile]
    return [str(item.get("error_code")) for item in failures if item.get("error_code")]


def _fault_terms(context: dict[str, Any]) -> set[str]:
    relevant = {
        "task": context.get("task"),
        "context": context.get("context"),
        "constraints": context.get("constraints"),
        "fault_profile": context.get("fault_profile"),
        "tags": context.get("tags"),
    }
    return _tokens(json.dumps(relevant, ensure_ascii=False))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower()))
