from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowledge_agent.feedback.updater import FeedbackUpdater
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.execution_checker import ExecutionChecker
from knowledge_agent.planner.tools import MockToolRegistry
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder
from knowledge_agent.tracing.schema import Trace


@dataclass
class AgentRunResult:
    task: str
    domain: str
    success: bool
    score: float
    plan: list[str]
    selected_skills: list[str] = field(default_factory=list)
    interactions: int = 0
    tool_calls: int = 0
    key_step_f1: float = 0.0
    recovered: bool = False
    trace: Trace | None = None
    failure_reason: str | None = None


class BaselineAgent:
    """A deterministic baseline planner without reusable trajectory knowledge."""

    def __init__(
        self,
        trace_dir: str | Path = "outputs/traces/baseline",
        tools: MockToolRegistry | None = None,
    ):
        self.tools = tools or MockToolRegistry()
        self.checker = ExecutionChecker(self.tools.tools)
        self.trace_dir = Path(trace_dir)

    def run(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | None = None,
    ) -> AgentRunResult:
        context = context or {}
        expected_steps = list(context.get("expected_steps", []))
        recorder = TraceRecorder(self.trace_dir)
        recorder.start(task, domain)
        plan = self.plan(task, domain, context)
        recovered = False

        for step in plan:
            self._execute_step(recorder, step, task)

        check = self.checker.check(plan, expected_steps, context=context)
        if not check.ok:
            recovered = self._naive_repair(recorder, plan, task)
            check = self.checker.check(plan, expected_steps, context=context)

        key_step_f1 = key_step_f1_score(plan, expected_steps)
        success = check.ok
        score = 1.0 if success else max(0.0, key_step_f1 - 0.25)
        failure_reason = None if success else f"missing_steps:{','.join(check.missing_steps)}"
        trace = recorder.finish(
            success=success,
            score=score,
            result="task_completed" if success else "task_failed",
            key_step_f1=key_step_f1,
            recovered=recovered and success,
            failure_reason=failure_reason,
        )
        return AgentRunResult(
            task=task,
            domain=domain,
            success=success,
            score=score,
            plan=plan,
            interactions=len(trace.steps),
            tool_calls=trace.result.tool_calls if trace.result else 0,
            key_step_f1=key_step_f1,
            recovered=recovered and success,
            trace=trace,
            failure_reason=failure_reason,
        )

    def plan(self, task: str, domain: str, context: dict[str, Any]) -> list[str]:
        plans = {
            "ai4science": ["collect_literature", "design_protocol", "generate_report"],
            "finance": ["extract_claim", "check_policy", "approve_or_reject"],
            "industrial": ["read_alarm", "select_recovery", "write_incident"],
        }
        return list(plans.get(domain, ["collect_literature", "generate_report"]))

    def _naive_repair(self, recorder: TraceRecorder, plan: list[str], task: str) -> bool:
        for repair in [
            "ask_for_more_context",
            "retry_tool",
            "manual_review",
            "select_alternative_tool",
            "retry_with_constraints",
        ]:
            if repair not in plan:
                plan.append(repair)
                self._execute_step(recorder, repair, task)
        return False

    def _execute_step(self, recorder: TraceRecorder, step: str, task: str) -> None:
        tool = self.checker.tool_for_step(step)
        result = self.tools.execute(tool, {"step": step, "task": task})
        recorder.record_step(
            state=f"ready:{step}",
            plan=step,
            action=step,
            tool_name=tool,
            tool_args={"step": step},
            observation=result.observation,
            error=result.error,
            reward=1.0 if result.success else -1.0,
        )


class KnowledgeEnhancedAgent(BaselineAgent):
    """Planner that retrieves Skill Graph knowledge before execution."""

    def __init__(
        self,
        skill_graph: SkillGraph,
        skill_store: SkillStore | None = None,
        trace_dir: str | Path = "outputs/traces/enhanced",
        tools: MockToolRegistry | None = None,
    ):
        super().__init__(trace_dir=trace_dir, tools=tools)
        self.skill_graph = skill_graph
        self.skill_store = skill_store

    def run(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | None = None,
    ) -> AgentRunResult:
        context = context or {}
        selected = self.skill_graph.retrieve(task, domain, context, top_k=3)
        expected_steps = list(context.get("expected_steps", []))
        recorder = TraceRecorder(self.trace_dir)
        recorder.start(task, domain)
        plan = self.plan_with_skills(task, domain, context, selected)
        recovered = False

        for step in plan:
            self._execute_step(recorder, step, task)

        check = self.checker.check(plan, expected_steps, selected, context)
        if check.known_risks:
            recovered = self._apply_rollback(recorder, plan, selected, task)
            check = self.checker.check(plan, expected_steps, selected, context)

        key_step_f1 = key_step_f1_score(plan, expected_steps)
        success = check.ok
        score = 1.0 if success else max(0.0, key_step_f1 - 0.1)
        failure_reason = None if success else f"missing_steps:{','.join(check.missing_steps)}"
        trace = recorder.finish(
            success=success,
            score=score,
            result="task_completed" if success else "task_failed",
            key_step_f1=key_step_f1,
            recovered=recovered,
            failure_reason=failure_reason,
        )
        if self.skill_store:
            FeedbackUpdater(self.skill_store).update_from_run(trace, selected)
        return AgentRunResult(
            task=task,
            domain=domain,
            success=success,
            score=score,
            plan=plan,
            selected_skills=[skill.skill_id for skill in selected],
            interactions=len(trace.steps),
            tool_calls=trace.result.tool_calls if trace.result else 0,
            key_step_f1=key_step_f1,
            recovered=recovered,
            trace=trace,
            failure_reason=failure_reason,
        )

    def plan_with_skills(
        self,
        task: str,
        domain: str,
        context: dict[str, Any],
        selected: list[SkillSpec],
    ) -> list[str]:
        plan = self.plan(task, domain, context)
        for skill in selected:
            for precondition in skill.preconditions:
                if precondition in {"task_goal_is_clear", "policy_context_available"}:
                    continue
                if precondition == "permission_context_available" and "validate_inputs" not in plan:
                    plan.insert(0, "validate_inputs")
            for step in skill.steps:
                if step not in plan:
                    insert_at = max(0, len(plan) - 1)
                    plan.insert(insert_at, step)
        for required in context.get("required_before_report", []):
            if required not in plan:
                plan.insert(max(0, len(plan) - 1), required)
        return dedupe_preserve_order(plan)

    def _apply_rollback(
        self,
        recorder: TraceRecorder,
        plan: list[str],
        selected: list[SkillSpec],
        task: str,
    ) -> bool:
        added = False
        for skill in selected:
            for step in skill.rollback:
                if step not in plan:
                    plan.append(step)
                    self._execute_step(recorder, step, task)
                    added = True
        return added


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def key_step_f1_score(predicted: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    predicted_set = set(predicted)
    expected_set = set(expected)
    tp = len(predicted_set & expected_set)
    if tp == 0:
        return 0.0
    precision = tp / len(predicted_set)
    recall = tp / len(expected_set)
    return round(2 * precision * recall / (precision + recall), 3)
