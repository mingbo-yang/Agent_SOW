from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from knowledge_agent.evaluation.result import key_step_f1_score
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder

try:
    from openjiuwen.core.foundation.tool import Tool, ToolCard
except Exception:  # pragma: no cover - exercised only without openJiuwen installed
    Tool = object  # type: ignore
    ToolCard = None  # type: ignore


STEP_TO_TOOL = {
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
}

@dataclass
class OpenJiuwenRunContext:
    task: str
    domain: str
    trace_recorder: TraceRecorder
    skill_store: SkillStore
    skill_graph: SkillGraph
    expected_steps: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    executed_steps: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str | None = None

    def start(self) -> str:
        self.trace_id = self.trace_recorder.start(self.task, self.domain)
        return self.trace_id

    def record_tool(
        self,
        tool_name: str,
        action: str,
        args: dict[str, Any],
        observation: str,
        error: str | None = None,
    ) -> None:
        if action in STEP_TO_TOOL:
            self.executed_steps.append(action)
        self.tool_calls.append(
            {
                "tool_name": tool_name,
                "action": action,
                "args": args,
                "observation": observation,
                "error": error,
            }
        )
        self.trace_recorder.record_step(
            state=f"openjiuwen_react:{action}",
            plan=action,
            action=action,
            tool_name=tool_name,
            tool_args=args,
            observation=observation,
            error=error,
            reward=1.0 if error is None else -1.0,
        )


def make_tool_card(name: str, description: str, properties: dict[str, Any] | None = None):
    if ToolCard is None:
        raise RuntimeError("openjiuwen is not installed")
    return ToolCard(
        id=name,
        name=name,
        description=description,
        input_params={
            "type": "object",
            "properties": properties
            or {
                "query": {"type": "string", "description": "Task or subtask query."},
                "context": {"type": "string", "description": "Additional context."},
            },
        },
        parallel_safe=False,
        stateless=False,
    )


class KnowledgeTool(Tool):
    def __init__(self, name: str, description: str, context: OpenJiuwenRunContext, properties=None):
        super().__init__(make_tool_card(name, description, properties))
        self.context = context

    async def stream(self, inputs: dict[str, Any], **kwargs) -> AsyncIterator[dict[str, Any]]:
        yield await self.invoke(inputs, **kwargs)


class RetrieveSkillsTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "retrieve_skills",
            "Retrieve reusable skills from the Skill Graph before planning or tool execution.",
            context,
            {
                "task": {"type": "string", "description": "Current user task."},
                "domain": {"type": "string", "description": "Task domain."},
                "context": {"type": "string", "description": "Extra task context."},
                "top_k": {"type": "integer", "description": "Number of skills to retrieve."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        task = str(inputs.get("task") or self.context.task)
        domain = str(inputs.get("domain") or self.context.domain)
        top_k = int(inputs.get("top_k") or 3)
        skills = self.context.skill_graph.retrieve(task, domain, inputs.get("context"), top_k=top_k)
        self.context.selected_skill_ids = [skill.skill_id for skill in skills]
        payload = {
            "skills": [skill_summary(skill) for skill in skills],
            "recommended_steps": merge_steps(skills),
        }
        self.context.record_tool(
            self.card.name,
            "retrieve_skills",
            inputs,
            json.dumps(payload, ensure_ascii=False),
        )
        return {"content": json.dumps(payload, ensure_ascii=False)}


class RecordTraceStepTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "record_trace_step",
            "Record an explicit planning or reasoning step into the audit trace.",
            context,
            {
                "plan": {"type": "string", "description": "Current plan."},
                "action": {"type": "string", "description": "Current action."},
                "observation": {"type": "string", "description": "Observation."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        action = str(inputs.get("action") or "manual_trace_step")
        observation = str(inputs.get("observation") or "")
        self.context.record_tool(self.card.name, action, inputs, observation)
        return {"content": f"recorded:{action}"}


class UpdateSkillFeedbackTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "update_skill_feedback",
            "Update skill confidence after task execution.",
            context,
            {
                "success": {"type": "boolean", "description": "Whether the task succeeded."},
                "failure_reason": {"type": "string", "description": "Failure reason if any."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        success = bool(inputs.get("success", True))
        failure_reason = inputs.get("failure_reason")
        for skill_id in self.context.selected_skill_ids:
            self.context.skill_store.update_feedback(
                skill_id,
                success=success,
                trace_id=self.context.trace_id,
                failure_pattern=str(failure_reason) if failure_reason else None,
            )
        self.context.record_tool(
            self.card.name,
            "update_skill_feedback",
            inputs,
            f"updated {len(self.context.selected_skill_ids)} skills",
        )
        return {"content": f"updated {len(self.context.selected_skill_ids)} skills"}


class ExportSkillGraphTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext, output_path: str | Path):
        super().__init__(
            "export_skill_graph",
            "Export the current Skill Graph to JSON for audit and visualization.",
            context,
            {"path": {"type": "string", "description": "Optional export path."}},
        )
        self.output_path = Path(output_path)

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        path = Path(inputs.get("path") or self.output_path)
        self.context.skill_graph.export_json(path)
        self.context.record_tool(self.card.name, "export_skill_graph", inputs, str(path))
        return {"content": str(path)}


class DomainTool(KnowledgeTool):
    def __init__(self, tool_name: str, description: str, action: str, context: OpenJiuwenRunContext):
        super().__init__(tool_name, description, context)
        self.action = action

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        action = "write_incident" if self.card.name == "report_writer" and self.context.domain == "industrial" else self.action
        observation = domain_observation(self.context.domain, self.card.name, inputs)
        self.context.record_tool(self.card.name, action, inputs, observation)
        return {"content": observation, "step": action, "tool": self.card.name}


def build_openjiuwen_tools(
    context: OpenJiuwenRunContext,
    enhanced: bool,
    graph_output_path: str | Path = "outputs/openjiuwen_skill_graph.json",
) -> list[KnowledgeTool]:
    tools: list[KnowledgeTool] = []
    if enhanced:
        tools.extend(
            [
                RetrieveSkillsTool(context),
                RecordTraceStepTool(context),
                UpdateSkillFeedbackTool(context),
                ExportSkillGraphTool(context, graph_output_path),
            ]
        )
    tools.extend(build_domain_tools(context))
    return tools


def build_domain_tools(context: OpenJiuwenRunContext) -> list[DomainTool]:
    common: dict[str, list[tuple[str, str, str]]] = {
        "ai4science": [
            ("literature_search", "Search AI4Science literature evidence.", "collect_literature"),
            ("paper_reader", "Extract variables and assumptions from papers.", "extract_variables"),
            ("schema_validator", "Validate task inputs and required metadata.", "validate_inputs"),
            ("protocol_designer", "Draft scientific experiment or data-analysis protocol.", "design_protocol"),
            ("constraint_checker", "Check scientific, safety, budget, or business constraints.", "verify_constraints"),
            ("report_writer", "Write final scientific report.", "generate_report"),
        ],
        "finance": [
            ("document_parser", "Parse finance claims, receipts, or loan packet documents.", "extract_claim"),
            ("policy_checker", "Check finance policy and compliance constraints.", "check_policy"),
            ("risk_scanner", "Scan duplicate, anomalous, or risky finance patterns.", "anomaly_check"),
            ("evidence_collector", "Collect supporting evidence for a decision.", "collect_evidence"),
            ("decision_engine", "Produce approve/reject/escalate decision.", "approve_or_reject"),
        ],
        "industrial": [
            ("monitoring_reader", "Read alarms and monitoring signals.", "read_alarm"),
            ("log_search", "Inspect operational logs.", "inspect_logs"),
            ("diagnosis_engine", "Perform root cause analysis.", "root_cause_analysis"),
            ("runbook_selector", "Select a recovery runbook.", "select_recovery"),
            ("health_checker", "Verify service or equipment recovery.", "verify_recovery"),
            ("report_writer", "Write final incident summary.", "write_incident"),
        ],
    }
    specs = common.get(context.domain, [spec for values in common.values() for spec in values])
    return [DomainTool(name, description, action, context) for name, description, action in specs]


def skill_summary(skill: SkillSpec) -> dict[str, Any]:
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "domain": skill.domain,
        "description": skill.description,
        "confidence": skill.confidence,
        "steps": skill.steps,
        "failure_patterns": skill.failure_patterns,
        "rollback": skill.rollback,
        "evidence_trace_ids": skill.evidence_trace_ids,
    }


def merge_steps(skills: list[SkillSpec]) -> list[str]:
    steps: list[str] = []
    for skill in skills:
        for step in skill.steps:
            if step not in steps:
                steps.append(step)
    return steps


def domain_observation(domain: str, tool_name: str, inputs: dict[str, Any]) -> str:
    query = str(inputs.get("query") or inputs.get("task") or "")
    context = str(inputs.get("context") or "")
    return (
        f"{tool_name} completed for domain={domain}; "
        f"query={query[:120]}; context={context[:120]}"
    )


def evaluate_openjiuwen_run(context: OpenJiuwenRunContext) -> tuple[bool, float, str | None]:
    expected = list(context.expected_steps)
    if not expected:
        return True, 1.0, None
    f1 = key_step_f1_score(context.executed_steps, expected)
    missing = [step for step in expected if step not in context.executed_steps]
    return not missing, f1, f"missing_steps:{','.join(missing)}" if missing else None
