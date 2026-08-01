from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from knowledge_agent.evaluation.result import AgentRunResult
from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.recorder import TraceRecorder, load_traces_jsonl
from knowledge_agent.openjiuwen_agent.tools import (
    OpenJiuwenRunContext,
    build_openjiuwen_tools,
    evaluate_openjiuwen_run,
)

try:
    from openjiuwen.core.runner.runner import Runner
    from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
    from openjiuwen.core.single_agent.schema.agent_card import AgentCard
except Exception:  # pragma: no cover
    Runner = None  # type: ignore
    ReActAgent = None  # type: ignore
    ReActAgentConfig = None  # type: ignore
    AgentCard = None  # type: ignore


class OpenJiuwenKnowledgeAgent:
    """openJiuwen ReActAgent-based knowledge-enhanced Agent."""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.deepseek.com",
        model_name: str = "deepseek-v4-flash",
        model_provider: str = "openai",
        skill_store_path: str | Path = "outputs/openjiuwen_runtime_skills.json",
        seed_trace_path: str | Path = "datasets/seed_traces.jsonl",
        trace_dir: str | Path = "outputs/openjiuwen_traces",
        graph_output_path: str | Path = "outputs/openjiuwen_skill_graph.json",
        max_iterations: int = 10,
    ):
        self._require_openjiuwen()
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name
        self.model_provider = model_provider
        self.skill_store = SkillStore(skill_store_path)
        self.seed_trace_path = Path(seed_trace_path)
        self.trace_dir = Path(trace_dir)
        self.graph_output_path = Path(graph_output_path)
        self.max_iterations = max_iterations
        self._bootstrap_skills()

    @classmethod
    def from_env(
        cls,
        skill_store_path: str | Path = "outputs/openjiuwen_runtime_skills.json",
        trace_dir: str | Path = "outputs/openjiuwen_traces",
        seed_trace_path: str | Path = "datasets/seed_traces.jsonl",
        max_iterations: int = 10,
    ) -> "OpenJiuwenKnowledgeAgent":
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENJIUWEN_API_KEY") or os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required for real openJiuwen ReAct runs.")
        return cls(
            api_key=api_key,
            api_base=os.getenv("DEEPSEEK_API_BASE") or os.getenv("OPENJIUWEN_API_BASE") or "https://api.deepseek.com",
            model_name=os.getenv("DEEPSEEK_MODEL") or os.getenv("MODEL_NAME") or "deepseek-v4-flash",
            model_provider=os.getenv("MODEL_PROVIDER", "openai"),
            skill_store_path=skill_store_path,
            seed_trace_path=seed_trace_path,
            trace_dir=trace_dir,
            max_iterations=max_iterations,
        )

    def run(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | None = None,
        enhanced: bool = True,
        agent_type: str | None = None,
    ) -> AgentRunResult:
        return asyncio.run(self.arun(task, domain, context=context, enhanced=enhanced, agent_type=agent_type))

    async def arun(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | None = None,
        enhanced: bool = True,
        agent_type: str | None = None,
    ) -> AgentRunResult:
        context = context or {}
        mode = agent_type or ("enhanced" if enhanced else "baseline")
        knowledge_mode = _knowledge_mode_for(mode, domain, context)
        graph = SkillGraph.build_from_skills(self.skill_store.list())
        graph.export_json(self.graph_output_path)
        run_context = OpenJiuwenRunContext(
            task=task,
            domain=domain,
            trace_recorder=TraceRecorder(self.trace_dir / mode),
            skill_store=self.skill_store,
            skill_graph=graph,
            expected_steps=list(context.get("expected_steps", [])),
            expected_recovery_steps=list(context.get("expected_recovery_steps", [])),
            required_before_report=list(context.get("required_before_report", [])),
            raw_context=context,
            agent_type=mode,
            knowledge_mode=knowledge_mode,
        )
        run_context.start()
        if mode == "enhanced":
            self._compile_internal_skill_plan(run_context, graph)
        agent = self._build_agent(domain=domain, agent_type=mode, knowledge_mode=knowledge_mode)
        tools = build_openjiuwen_tools(
            run_context,
            agent_type=mode,
            graph_output_path=self.graph_output_path,
            knowledge_mode=knowledge_mode,
        )
        run_context.trace_recorder.update_metadata(
            agent=agent.card.id,
            model=self.model_name,
            audit={
                "openjiuwen_available": True,
                "openjiuwen_agent_class": "ReActAgent",
                "model_provider": self.model_provider,
                "api_base": self.api_base,
                "agent_type": mode,
                "enhanced": mode == "enhanced",
                "knowledge_mode": knowledge_mode,
                "registered_tools": [tool.card.name for tool in tools],
                "task_id": context.get("task_id"),
                "fault_profile": context.get("fault_profile"),
            },
        )
        self._register_tools(agent, tools)

        prompt = self._build_task_prompt(task, domain, context, mode, run_context)
        started_at = time.perf_counter()
        conversation_id = f"{agent.card.id}_{run_context.trace_id}"
        raw_output = await self._invoke_agent(agent, prompt, conversation_id=conversation_id)
        if mode == "enhanced" and run_context.unresolved_faults():
            run_context.apply_structured_recovery()
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        success, key_step_f1, failure_reason, required_order_ok = evaluate_openjiuwen_run(run_context)
        selected_skills = [
            skill for skill in self.skill_store.list() if skill.skill_id in run_context.selected_skill_ids
        ]
        run_context.trace_recorder.update_metadata(
            audit={
                "selected_skills": list(run_context.selected_skill_ids),
                "executed_steps": list(run_context.executed_steps),
                "tool_call_names": [item["tool_name"] for item in run_context.tool_calls],
                "skill_plan": run_context.skill_plan.to_dict(),
                "plan_warnings": list(run_context.skill_plan.plan_warnings),
                "blocked_reasons": list(run_context.skill_plan.blocked_reasons),
                "matched_failure_patterns": list(run_context.matched_failure_patterns),
                "detected_faults": sorted(run_context.detected_faults),
                "rollback_used": run_context.rollback_used,
                "recovery_success": run_context.recovery_success,
                "required_order_ok": required_order_ok,
                "latency_ms": latency_ms,
            }
        )
        trace = run_context.trace_recorder.finish(
            success=success,
            score=1.0 if success else max(0.0, key_step_f1 - 0.25),
            result=self._stringify_output(raw_output),
            key_step_f1=key_step_f1,
            recovered=run_context.recovery_success,
            failure_reason=failure_reason,
        )
        if selected_skills:
            from knowledge_agent.feedback.updater import FeedbackUpdater

            FeedbackUpdater(self.skill_store).update_from_run(trace, selected_skills)
        return AgentRunResult(
            task=task,
            domain=domain,
            success=success,
            score=trace.result.score if trace.result else 0.0,
            plan=list(run_context.executed_steps),
            agent_type=mode,
            task_id=context.get("task_id"),
            selected_skills=list(run_context.selected_skill_ids),
            interactions=len(trace.steps),
            tool_calls=trace.result.tool_calls if trace.result else len(run_context.tool_calls),
            key_step_f1=key_step_f1,
            recovered=run_context.recovery_success,
            trace=trace,
            failure_reason=failure_reason,
            failure_detected=bool(run_context.detected_faults),
            matched_failure_patterns=list(run_context.matched_failure_patterns),
            rollback_used=run_context.rollback_used,
            recovery_success=run_context.recovery_success,
            required_order_ok=required_order_ok,
            latency_ms=latency_ms,
        )

    def _build_agent(self, domain: str, agent_type: str, knowledge_mode: str = "off") -> ReActAgent:
        agent_id = f"zju_knowledge_react_{domain}_{agent_type}"
        agent = ReActAgent(
            card=AgentCard(
                id=agent_id,
                name=agent_id,
                description="Knowledge-enhanced openJiuwen ReAct Agent",
            )
        )
        config = (
            ReActAgentConfig()
            .configure_model_client(
                provider=self.model_provider,
                api_key=self.api_key,
                api_base=self.api_base,
                model_name=self.model_name,
                verify_ssl=False,
            )
            .configure_prompt_template([{"role": "system", "content": self._system_prompt(agent_type, knowledge_mode)}])
            .configure_max_iterations(self.max_iterations)
            .configure_parallel_tool_calls(False)
            .configure_context_engine(max_context_message_num=None, default_window_round_num=None)
        )
        agent.configure(config)
        return agent

    def _register_tools(self, agent: ReActAgent, tools: list[Any]) -> None:
        Runner.resource_mgr.add_tool(tool=tools, tag=agent.card.id, refresh=True)
        agent.ability_manager.add([tool.card for tool in tools])

    async def _invoke_agent(self, agent: ReActAgent, prompt: str, conversation_id: str) -> Any:
        try:
            return await agent.invoke({"query": prompt, "conversation_id": conversation_id})
        except Exception:
            # Current openJiuwen docs note that ReActAgent should use invoke()
            # directly, but keep Runner fallback for compatible versions.
            return await Runner.run_agent(
                agent=agent,
                inputs={"query": prompt, "conversation_id": conversation_id},
            )

    def _build_task_prompt(
        self,
        task: str,
        domain: str,
        context: dict[str, Any],
        agent_type: str,
        run_context: OpenJiuwenRunContext,
    ) -> str:
        expected = context.get("expected_steps", [])
        expected_recovery = context.get("expected_recovery_steps", [])
        expected_text = ", ".join(expected)
        recovery_text = ", ".join(expected_recovery)
        skill_instruction = self._mode_instruction(agent_type, run_context)
        prompt_context = _redact_context_for_prompt(context)
        return (
            f"Mode: {agent_type}\n"
            f"Domain: {domain}\n"
            f"Task: {task}\n"
            f"Context JSON: {json.dumps(prompt_context, ensure_ascii=False)}\n"
            f"Expected key steps for evaluation: {expected_text}\n"
            f"Expected recovery steps when faults occur: {recovery_text}\n"
            f"Precomputed SkillPlan JSON: {json.dumps(_compact_skill_plan(run_context), ensure_ascii=False)}\n"
            f"{skill_instruction}\n"
            "Use tools rather than only answering from memory. Call the relevant tools in a complete order. "
            "If a tool observation contains needs_recovery=true, address the recovery before final answer. "
            "Finish with a short JSON-like summary containing success, used_steps, and final_answer."
        )

    def _system_prompt(self, agent_type: str, knowledge_mode: str = "off") -> str:
        base = (
            "You are an enterprise ReAct agent running inside openJiuwen. "
            "You solve tasks by reasoning, selecting tools, observing results, and then producing a final answer. "
            "Use only registered tools. Keep tool arguments small and valid JSON. "
        )
        if agent_type == "enhanced":
            if knowledge_mode == "full":
                return (
                    base
                    + "A compact Skill Graph plan is already included in the task prompt. "
                    + "Follow its domain step order. Use recovery tools only after a tool observation has needs_recovery=true "
                    + "or when the fault profile explicitly requires the matching rollback step."
                )
            return (
                base
                + "A compact Skill Graph plan is already included in the task prompt as an ordering hint. "
                + "Do not spend tool calls on skill retrieval or audit logging; solve with the domain tools only."
            )
        if agent_type == "rag":
            return base + "Call retrieve_reference_docs first, then solve with domain tools. Do not use skills."
        if agent_type == "memory":
            return base + "Call retrieve_raw_memory first, then solve with domain tools. Do not use structured skills."
        return base + "Solve with domain tools only; do not use skill retrieval or memory tools."

    def _mode_instruction(self, agent_type: str, run_context: OpenJiuwenRunContext) -> str:
        if agent_type == "enhanced":
            if run_context.knowledge_mode == "full":
                return (
                    "Use the precomputed SkillPlan as the execution guide. "
                    "If needs_recovery=true appears, match skill_plan.matched_failure_patterns or rollback_steps and call the relevant recovery tool before continuing. "
                    "Avoid audit-only tool calls; prioritize expected domain steps and required recovery steps."
                )
            if run_context.domain == "agentbench_db":
                return (
                    "Use the precomputed SkillPlan only as a compact SQL workflow hint. "
                    "Do not call any skill or recovery tools. Execute in this order: db_schema_reader, sql_query_executor, answer_submitter."
                )
            return (
                "Use the precomputed SkillPlan only as a compact ordering hint. "
                "No recovery tools are needed for this task; execute the expected domain steps directly and keep their order."
            )
        if agent_type == "rag":
            return "First call retrieve_reference_docs. Use only static references and domain tools; no skills or rollback plans are available."
        if agent_type == "memory":
            return "First call retrieve_raw_memory. Use raw memories as hints only; no structured Skill Graph plan is available."
        return "Do not call retrieve_skills. Use only domain tools and your own planning."

    def _compile_internal_skill_plan(self, run_context: OpenJiuwenRunContext, graph: SkillGraph) -> None:
        from knowledge_agent.openjiuwen_agent.planner import compile_skill_plan

        skills = graph.retrieve(run_context.task, run_context.domain, run_context.raw_context, top_k=3)
        run_context.selected_skill_ids = [skill.skill_id for skill in skills]
        run_context.skill_plan = compile_skill_plan(skills, run_context.raw_context)
        run_context.matched_failure_patterns = list(run_context.skill_plan.matched_failure_patterns)

    def _bootstrap_skills(self) -> None:
        if self.skill_store.list():
            return
        traces = load_traces_jsonl(self.seed_trace_path)
        skills = SkillExtractor().extract_from_traces(traces)
        self.skill_store.save_many(skills)

    def _stringify_output(self, output: Any) -> str:
        if isinstance(output, dict):
            return json.dumps(output, ensure_ascii=False)
        return str(output)

    def _require_openjiuwen(self) -> None:
        if ReActAgent is None:
            raise RuntimeError("openjiuwen is not installed. Use .venv or install openjiuwen first.")


def _redact_context_for_prompt(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).startswith("_private"):
                continue
            if key in {"label", "answer", "expected_answer", "gold", "sql", "dbbench_fixture", "rows", "tables"}:
                continue
            redacted[key] = _redact_context_for_prompt(item)
        return redacted
    if isinstance(value, list):
        return [_redact_context_for_prompt(item) for item in value]
    return value


def _knowledge_mode_for(agent_type: str, domain: str, context: dict[str, Any]) -> str:
    if agent_type != "enhanced":
        return "off"
    if _has_fault_profile(context) or context.get("expected_recovery_steps"):
        return "full"
    if domain == "agentbench_db":
        return "lite_sql"
    return "lite"


def _has_fault_profile(context: dict[str, Any]) -> bool:
    profile = context.get("fault_profile") or {}
    failures = profile.get("failures") or []
    return bool(failures or profile.get("error_code"))


def _compact_skill_plan(run_context: OpenJiuwenRunContext) -> dict[str, Any]:
    if run_context.agent_type != "enhanced":
        return {}
    plan = run_context.skill_plan
    return {
        "knowledge_mode": run_context.knowledge_mode,
        "selected_skill_ids": list(run_context.selected_skill_ids),
        "ordered_steps": _limit(plan.ordered_steps, 8),
        "failure_patterns": _limit(plan.failure_patterns, 6),
        "rollback_steps": _limit(plan.rollback_steps, 6),
        "matched_failure_patterns": _limit(plan.matched_failure_patterns, 6),
        "plan_warnings": _limit(plan.plan_warnings, 4),
        "blocked_reasons": _limit(plan.blocked_reasons, 4),
    }


def _limit(items: list[str], max_items: int) -> list[str]:
    return [str(item) for item in items[:max_items]]
