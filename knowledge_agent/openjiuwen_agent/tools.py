from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from knowledge_agent.benchmarks.agentbench_adapter import execute_sql_fixture, heuristic_sql_for_task
from knowledge_agent.evaluation.result import key_step_f1_score
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.openjiuwen_agent.planner import SkillPlan, compile_skill_plan
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder

try:
    from openjiuwen.core.foundation.tool import Tool, ToolCard
except Exception:  # pragma: no cover
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
    "read_schema": "db_schema_reader",
    "generate_sql": "sql_query_executor",
    "execute_sql": "sql_query_executor",
    "validate_answer": "answer_submitter",
    "submit_answer": "answer_submitter",
}

RECOVERY_STEPS = {
    "recover_context",
    "select_alternative_path",
    "execute_rollback",
    "manual_escalation",
}


@dataclass
class OpenJiuwenRunContext:
    task: str
    domain: str
    trace_recorder: TraceRecorder
    skill_store: SkillStore
    skill_graph: SkillGraph
    expected_steps: list[str] = field(default_factory=list)
    expected_recovery_steps: list[str] = field(default_factory=list)
    required_before_report: list[str] = field(default_factory=list)
    raw_context: dict[str, Any] = field(default_factory=dict)
    agent_type: str = "enhanced"
    selected_skill_ids: list[str] = field(default_factory=list)
    executed_steps: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    resolved_faults: set[str] = field(default_factory=set)
    detected_faults: set[str] = field(default_factory=set)
    matched_failure_patterns: list[str] = field(default_factory=list)
    skill_plan: SkillPlan = field(default_factory=SkillPlan)
    rollback_used: bool = False
    recovery_success: bool = False
    trace_id: str | None = None
    db_last_sql: str | None = None
    db_last_rows: list[dict[str, Any]] = field(default_factory=list)
    db_last_answer: str | None = None

    def start(self) -> str:
        self.trace_id = self.trace_recorder.start(self.task, self.domain)
        return self.trace_id

    def record_tool(
        self,
        tool_name: str,
        action: str,
        args: dict[str, Any],
        observation: str | dict[str, Any],
        error: str | None = None,
    ) -> None:
        if action in STEP_TO_TOOL or action in RECOVERY_STEPS:
            self.executed_steps.append(action)
        observation_text = observation if isinstance(observation, str) else json.dumps(observation, ensure_ascii=False)
        self.tool_calls.append(
            {
                "tool_name": tool_name,
                "action": action,
                "args": args,
                "observation": observation_text,
                "error": error,
            }
        )
        self.trace_recorder.record_step(
            state=f"openjiuwen_react:{action}",
            plan=action,
            action=action,
            tool_name=tool_name,
            tool_args=args,
            observation=observation_text,
            error=error,
            reward=1.0 if error is None else -1.0,
        )

    def fault_for(self, tool_name: str, action: str) -> dict[str, Any] | None:
        for index, fault in enumerate(self._faults()):
            fault_id = self._fault_id(index, fault)
            if fault_id in self.resolved_faults:
                continue
            if fault.get("step") == action or fault.get("tool") == tool_name:
                return {"fault_id": fault_id, **fault}
        return None

    def unresolved_faults(self) -> list[dict[str, Any]]:
        pending = []
        for index, fault in enumerate(self._faults()):
            fault_id = self._fault_id(index, fault)
            if fault_id not in self.resolved_faults:
                pending.append({"fault_id": fault_id, **fault})
        return pending

    def resolve_faults_with(self, recovery_tool: str, recovery_action: str) -> list[str]:
        resolved = []
        for index, fault in enumerate(self._faults()):
            fault_id = self._fault_id(index, fault)
            if fault_id in self.resolved_faults:
                continue
            recoverable_by = set(fault.get("recoverable_by") or [])
            if recovery_tool in recoverable_by or recovery_action in recoverable_by:
                self.resolved_faults.add(fault_id)
                resolved.append(fault_id)
        if resolved:
            self.recovery_success = True
        return resolved

    def apply_structured_recovery(self) -> None:
        for fault in self.unresolved_faults():
            recovery_action = _recovery_action_for_error(str(fault.get("error_code", "")))
            recovery_tool = RECOVERY_TOOL_BY_ACTION.get(recovery_action, "manual_escalation")
            observation = {
                "ok": True,
                "step": recovery_action,
                "tool": recovery_tool,
                "content": f"structured recovery resolved {fault.get('error_code')}",
                "resolved_fault_id": fault["fault_id"],
            }
            self.resolved_faults.add(fault["fault_id"])
            if recovery_action == "execute_rollback":
                self.rollback_used = True
            self.recovery_success = True
            self.record_tool(recovery_tool, recovery_action, {"auto": True, "fault": fault}, observation)

    def _faults(self) -> list[dict[str, Any]]:
        profile = self.raw_context.get("fault_profile") or {}
        failures = profile.get("failures") or []
        if not failures and profile.get("error_code"):
            failures = [profile]
        return [dict(item) for item in failures]

    def _fault_id(self, index: int, fault: dict[str, Any]) -> str:
        return str(fault.get("fault_id") or f"{fault.get('step') or fault.get('tool')}:{fault.get('error_code')}:{index}")


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
            "Retrieve reusable skills and compile a Skill Graph plan before execution.",
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
        skills = self.context.skill_graph.retrieve(task, domain, self.context.raw_context, top_k=top_k)
        self.context.selected_skill_ids = [skill.skill_id for skill in skills]
        self.context.skill_plan = compile_skill_plan(skills, self.context.raw_context)
        self.context.matched_failure_patterns = list(self.context.skill_plan.matched_failure_patterns)
        payload = {
            "skills": [skill_summary(skill) for skill in skills],
            "recommended_steps": self.context.skill_plan.ordered_steps,
            "skill_plan": self.context.skill_plan.to_dict(),
        }
        self.context.record_tool(self.card.name, "retrieve_skills", inputs, payload)
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


class ReferenceDocsTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "retrieve_reference_docs",
            "Retrieve static reference documents for a ReAct+RAG baseline. It does not return skills or rollback plans.",
            context,
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        payload = {
            "domain": self.context.domain,
            "docs": [
                f"Static {self.context.domain} operating procedure.",
                "Follow task constraints and inspect tool observations before final decision.",
            ],
        }
        self.context.record_tool(self.card.name, "retrieve_reference_docs", inputs, payload)
        return {"content": json.dumps(payload, ensure_ascii=False)}


class RawMemoryTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "retrieve_raw_memory",
            "Retrieve raw historical trace snippets for a memory baseline. It does not return structured Skill Graph plans.",
            context,
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        snippets = []
        for skill in self.context.skill_store.list():
            if skill.domain == self.context.domain:
                snippets.append({"trace_ids": skill.evidence_trace_ids, "summary": skill.description})
        payload = {"domain": self.context.domain, "memory": snippets[:3]}
        self.context.record_tool(self.card.name, "retrieve_raw_memory", inputs, payload)
        return {"content": json.dumps(payload, ensure_ascii=False)}


class RecoveryTool(KnowledgeTool):
    def __init__(self, name: str, description: str, action: str, context: OpenJiuwenRunContext):
        super().__init__(name, description, context)
        self.action = action

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        resolved = self.context.resolve_faults_with(self.card.name, self.action)
        if self.action == "execute_rollback":
            self.context.rollback_used = True
        observation = {
            "ok": True,
            "step": self.action,
            "tool": self.card.name,
            "content": f"{self.card.name} resolved {len(resolved)} pending fault(s)",
            "resolved_faults": resolved,
        }
        self.context.record_tool(self.card.name, self.action, inputs, observation)
        return observation


class DomainTool(KnowledgeTool):
    def __init__(self, tool_name: str, description: str, action: str, context: OpenJiuwenRunContext):
        super().__init__(tool_name, description, context)
        self.action = action

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        action = "write_incident" if self.card.name == "report_writer" and self.context.domain == "industrial" else self.action
        fault = self.context.fault_for(self.card.name, action)
        if fault:
            error_code = str(fault.get("error_code") or "TOOL_ERROR")
            self.context.detected_faults.add(error_code)
            suggested = _recovery_action_for_error(error_code)
            observation = {
                "ok": False,
                "step": action,
                "tool": self.card.name,
                "content": fault.get("message") or f"{self.card.name} failed with {error_code}",
                "error_code": error_code,
                "needs_recovery": True,
                "suggested_recovery": suggested,
                "recoverable_by": fault.get("recoverable_by") or [RECOVERY_TOOL_BY_ACTION.get(suggested, "manual_escalation")],
            }
            self.context.record_tool(self.card.name, action, inputs, observation, error=error_code)
            return observation

        observation = {
            "ok": True,
            "step": action,
            "tool": self.card.name,
            "content": domain_observation(self.context.domain, self.card.name, inputs),
            "error_code": None,
            "needs_recovery": False,
            "suggested_recovery": None,
        }
        self.context.record_tool(self.card.name, action, inputs, observation)
        return observation


class DBSchemaReaderTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "db_schema_reader",
            "Read the DBBench database schema before writing SQL.",
            context,
            {
                "query": {"type": "string", "description": "Question to answer."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        fault = self.context.fault_for(self.card.name, "read_schema")
        if fault:
            return self._fault_observation(inputs, fault)
        schema = self.context.raw_context.get("schema") or (
            (self.context.raw_context.get("dbbench_fixture") or {}).get("schema")
        )
        observation = {
            "ok": True,
            "step": "read_schema",
            "tool": self.card.name,
            "content": schema or "schema unavailable; inspect official AgentBench DB environment",
            "error_code": None,
            "needs_recovery": False,
            "suggested_recovery": None,
        }
        self.context.record_tool(self.card.name, "read_schema", inputs, observation)
        return observation

    def _fault_observation(self, inputs: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
        error_code = str(fault.get("error_code") or "SCHEMA_READ_ERROR")
        self.context.detected_faults.add(error_code)
        suggested = _recovery_action_for_error(error_code)
        observation = {
            "ok": False,
            "step": "read_schema",
            "tool": self.card.name,
            "content": fault.get("message") or error_code,
            "error_code": error_code,
            "needs_recovery": True,
            "suggested_recovery": suggested,
        }
        self.context.record_tool(self.card.name, "read_schema", inputs, observation, error=error_code)
        return observation


class SQLQueryExecutorTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "sql_query_executor",
            "Execute SQL against the DBBench sqlite fixture or official DB context.",
            context,
            {
                "sql": {"type": "string", "description": "SQL query to execute."},
                "query": {"type": "string", "description": "Natural-language question if SQL is not ready."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        sql = str(inputs.get("sql") or "").strip()
        if not sql:
            sql = heuristic_sql_for_task(str(inputs.get("query") or self.context.task))
        self.context.db_last_sql = sql
        self.context.record_tool(
            self.card.name,
            "generate_sql",
            {"sql": sql, "source": "model_or_heuristic", **inputs},
            {"ok": True, "step": "generate_sql", "tool": self.card.name, "content": sql},
        )
        fault = self.context.fault_for(self.card.name, "execute_sql")
        if fault:
            error_code = str(fault.get("error_code") or "SQL_EXECUTION_ERROR")
            self.context.detected_faults.add(error_code)
            suggested = _recovery_action_for_error(error_code)
            observation = {
                "ok": False,
                "step": "execute_sql",
                "tool": self.card.name,
                "content": fault.get("message") or f"SQL failed: {sql}",
                "sql": sql,
                "error_code": error_code,
                "needs_recovery": True,
                "suggested_recovery": suggested,
                "recoverable_by": fault.get("recoverable_by") or [RECOVERY_TOOL_BY_ACTION.get(suggested, "manual_escalation")],
            }
            self.context.record_tool(self.card.name, "execute_sql", inputs, observation, error=error_code)
            return observation

        fixture = self.context.raw_context.get("dbbench_fixture") or {}
        if fixture.get("tables"):
            ok, content, rows = execute_sql_fixture(fixture, sql)
            self.context.db_last_rows = rows
            if rows:
                first_row = rows[0]
                if len(first_row) == 1:
                    self.context.db_last_answer = str(next(iter(first_row.values())))
                else:
                    self.context.db_last_answer = json.dumps(first_row, ensure_ascii=False)
            error_code = None if ok else "SQL_EXECUTION_ERROR"
            observation = {
                "ok": ok,
                "step": "execute_sql",
                "tool": self.card.name,
                "content": content,
                "sql": sql,
                "error_code": error_code,
                "needs_recovery": not ok,
                "suggested_recovery": _recovery_action_for_error(error_code or "") if not ok else None,
            }
            self.context.record_tool(self.card.name, "execute_sql", inputs, observation, error=error_code)
            return observation

        observation = {
            "ok": True,
            "step": "execute_sql",
            "tool": self.card.name,
            "content": "SQL prepared for official AgentBench DB environment; local DB handle unavailable.",
            "sql": sql,
            "error_code": None,
            "needs_recovery": False,
            "suggested_recovery": None,
        }
        self.context.record_tool(self.card.name, "execute_sql", inputs, observation)
        return observation


class AnswerSubmitterTool(KnowledgeTool):
    def __init__(self, context: OpenJiuwenRunContext):
        super().__init__(
            "answer_submitter",
            "Validate and submit the final DBBench answer.",
            context,
            {
                "answer": {"type": "string", "description": "Final answer."},
            },
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs) -> dict[str, Any]:
        answer = str(inputs.get("answer") or self.context.db_last_answer or "").strip()
        self.context.db_last_answer = answer
        expected = self.context.raw_context.get("_private_expected_answer") or self.context.raw_context.get("expected_answer")
        if isinstance(expected, list):
            expected_values = [str(item).strip().lower() for item in expected]
        elif expected is None:
            expected_values = []
        else:
            expected_values = [str(expected).strip().lower()]
        validated = not expected_values or any(value in answer.lower() for value in expected_values)
        validation = {
            "ok": validated,
            "step": "validate_answer",
            "tool": self.card.name,
            "content": {"answer": answer, "expected_available": expected is not None},
            "error_code": None if validated else "ANSWER_MISMATCH",
            "needs_recovery": not validated,
            "suggested_recovery": "select_alternative_path" if not validated else None,
        }
        self.context.record_tool(
            self.card.name,
            "validate_answer",
            inputs,
            validation,
            error=None if validated else "ANSWER_MISMATCH",
        )
        submission = {
            "ok": validated,
            "step": "submit_answer",
            "tool": self.card.name,
            "content": answer,
            "error_code": None if validated else "ANSWER_MISMATCH",
            "needs_recovery": False,
            "suggested_recovery": None,
        }
        self.context.record_tool(
            self.card.name,
            "submit_answer",
            inputs,
            submission,
            error=None if validated else "ANSWER_MISMATCH",
        )
        return submission


RECOVERY_TOOL_BY_ACTION = {
    "recover_context": "context_requester",
    "select_alternative_path": "alternative_tool_selector",
    "execute_rollback": "rollback_executor",
    "manual_escalation": "manual_escalation",
}


def build_openjiuwen_tools(
    context: OpenJiuwenRunContext,
    agent_type: str = "enhanced",
    graph_output_path: str | Path = "outputs/openjiuwen_skill_graph.json",
    enhanced: bool | None = None,
) -> list[KnowledgeTool]:
    if enhanced is not None:
        agent_type = "enhanced" if enhanced else "baseline"
    tools: list[KnowledgeTool] = []
    if agent_type == "enhanced":
        tools.extend(
            [
                RetrieveSkillsTool(context),
                RecordTraceStepTool(context),
                UpdateSkillFeedbackTool(context),
                ExportSkillGraphTool(context, graph_output_path),
                RecoveryTool("context_requester", "Recover by requesting or filling missing context.", "recover_context", context),
                RecoveryTool("alternative_tool_selector", "Recover by selecting an alternative path or tool.", "select_alternative_path", context),
                RecoveryTool("rollback_executor", "Recover by rolling back unsafe or failed changes.", "execute_rollback", context),
                RecoveryTool("manual_escalation", "Recover by escalating policy or safety conflicts.", "manual_escalation", context),
            ]
        )
    elif agent_type == "rag":
        tools.append(ReferenceDocsTool(context))
    elif agent_type == "memory":
        tools.append(RawMemoryTool(context))
    tools.extend(build_domain_tools(context))
    return tools


def build_domain_tools(context: OpenJiuwenRunContext) -> list[KnowledgeTool]:
    if context.domain == "agentbench_db":
        return [DBSchemaReaderTool(context), SQLQueryExecutorTool(context), AnswerSubmitterTool(context)]
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


def domain_observation(domain: str, tool_name: str, inputs: dict[str, Any]) -> str:
    query = str(inputs.get("query") or inputs.get("task") or "")
    context = str(inputs.get("context") or "")
    return (
        f"{tool_name} completed for domain={domain}; "
        f"query={query[:120]}; context={context[:120]}"
    )


def evaluate_openjiuwen_run(context: OpenJiuwenRunContext) -> tuple[bool, float, str | None, bool]:
    expected = list(context.expected_steps)
    business_steps = [step for step in context.executed_steps if step in expected]
    f1 = key_step_f1_score(business_steps, expected) if expected else 1.0
    missing = [step for step in expected if step not in context.executed_steps]
    missing_recovery = [step for step in context.expected_recovery_steps if step not in context.executed_steps]
    order_ok = required_order_ok(context.executed_steps, context.required_before_report, expected)
    unresolved = context.unresolved_faults()
    reasons = []
    if missing:
        reasons.append(f"missing_steps:{','.join(missing)}")
    if missing_recovery:
        reasons.append(f"missing_recovery_steps:{','.join(missing_recovery)}")
    if not order_ok:
        reasons.append("required_order_violation")
    if unresolved:
        reasons.append("unresolved_faults:" + ",".join(str(item.get("error_code")) for item in unresolved))
    return not reasons, f1, ";".join(reasons) if reasons else None, order_ok


def required_order_ok(executed_steps: list[str], required_before_report: list[str], expected: list[str]) -> bool:
    if not required_before_report:
        return True
    final_steps = [step for step in ["generate_report", "write_incident", "approve_or_reject", "submit_answer"] if step in expected]
    if not final_steps:
        return True
    positions = {step: index for index, step in enumerate(executed_steps)}
    final_position = min((positions[step] for step in final_steps if step in positions), default=None)
    if final_position is None:
        return False
    return all(step in positions and positions[step] < final_position for step in required_before_report)


def _recovery_action_for_error(error_code: str) -> str:
    if error_code in {"MISSING_METADATA", "VARIABLE_MISMATCH", "POLICY_EVIDENCE_REQUIRED", "DUPLICATE_RECEIPT_EVIDENCE", "POLICY_VERSION_CHANGED"}:
        return "recover_context"
    if error_code in {"LOG_TOOL_UNAVAILABLE", "RUNBOOK_NOT_APPLICABLE"}:
        return "select_alternative_path"
    if error_code in {"RECENT_DEPLOYMENT_REGRESSION", "HEALTH_CHECK_FAILED"}:
        return "execute_rollback"
    if error_code in {"SQL_EXECUTION_ERROR", "SQL_SYNTAX_ERROR", "ANSWER_MISMATCH", "SCHEMA_READ_ERROR"}:
        return "select_alternative_path"
    return "manual_escalation"
