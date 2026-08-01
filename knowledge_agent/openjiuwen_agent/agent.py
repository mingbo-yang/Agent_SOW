from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.agent import AgentRunResult
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
    ) -> AgentRunResult:
        return asyncio.run(self.arun(task, domain, context=context, enhanced=enhanced))

    async def arun(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | None = None,
        enhanced: bool = True,
    ) -> AgentRunResult:
        context = context or {}
        graph = SkillGraph.build_from_skills(self.skill_store.list())
        graph.export_json(self.graph_output_path)
        run_context = OpenJiuwenRunContext(
            task=task,
            domain=domain,
            trace_recorder=TraceRecorder(self.trace_dir / ("enhanced" if enhanced else "baseline")),
            skill_store=self.skill_store,
            skill_graph=graph,
            expected_steps=list(context.get("expected_steps", [])),
        )
        run_context.start()
        agent = self._build_agent(domain=domain, enhanced=enhanced)
        tools = build_openjiuwen_tools(run_context, enhanced=enhanced, graph_output_path=self.graph_output_path)
        run_context.trace_recorder.update_metadata(
            agent=agent.card.id,
            model=self.model_name,
            audit={
                "openjiuwen_available": True,
                "openjiuwen_agent_class": "ReActAgent",
                "model_provider": self.model_provider,
                "api_base": self.api_base,
                "enhanced": enhanced,
                "registered_tools": [tool.card.name for tool in tools],
            },
        )
        self._register_tools(agent, tools)

        prompt = self._build_task_prompt(task, domain, context, enhanced)
        raw_output = await self._invoke_agent(agent, prompt)
        success, key_step_f1, failure_reason = evaluate_openjiuwen_run(run_context)
        selected_skills = [
            skill for skill in self.skill_store.list() if skill.skill_id in run_context.selected_skill_ids
        ]
        run_context.trace_recorder.update_metadata(
            audit={
                "selected_skills": list(run_context.selected_skill_ids),
                "executed_steps": list(run_context.executed_steps),
                "tool_call_names": [item["tool_name"] for item in run_context.tool_calls],
            }
        )
        trace = run_context.trace_recorder.finish(
            success=success,
            score=1.0 if success else key_step_f1,
            result=self._stringify_output(raw_output),
            key_step_f1=key_step_f1,
            recovered=success and bool(run_context.selected_skill_ids),
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
            selected_skills=list(run_context.selected_skill_ids),
            interactions=len(trace.steps),
            tool_calls=trace.result.tool_calls if trace.result else len(run_context.tool_calls),
            key_step_f1=key_step_f1,
            recovered=success and bool(run_context.selected_skill_ids),
            trace=trace,
            failure_reason=failure_reason,
        )

    def _build_agent(self, domain: str, enhanced: bool) -> ReActAgent:
        agent_id = f"zju_knowledge_react_{domain}_{'enhanced' if enhanced else 'baseline'}"
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
            .configure_prompt_template([{"role": "system", "content": self._system_prompt(enhanced)}])
            .configure_max_iterations(self.max_iterations)
            .configure_parallel_tool_calls(False)
            .configure_context_engine(max_context_message_num=None, default_window_round_num=None)
        )
        agent.configure(config)
        return agent

    def _register_tools(self, agent: ReActAgent, tools: list[Any]) -> None:
        Runner.resource_mgr.add_tool(tool=tools, tag=agent.card.id, refresh=True)
        agent.ability_manager.add([tool.card for tool in tools])

    async def _invoke_agent(self, agent: ReActAgent, prompt: str) -> Any:
        try:
            return await agent.invoke({"query": prompt, "conversation_id": f"{agent.card.id}_conv"})
        except Exception:
            # Current openJiuwen docs note that ReActAgent should use invoke()
            # directly, but keep Runner fallback for compatible versions.
            return await Runner.run_agent(
                agent=agent,
                inputs={"query": prompt, "conversation_id": f"{agent.card.id}_conv"},
            )

    def _build_task_prompt(
        self,
        task: str,
        domain: str,
        context: dict[str, Any],
        enhanced: bool,
    ) -> str:
        expected = context.get("expected_steps", [])
        expected_text = ", ".join(expected)
        mode = "enhanced" if enhanced else "baseline"
        skill_instruction = (
            "First call retrieve_skills with the task/domain/context, then follow the returned recommended_steps. "
            "After using domain tools, provide a concise final answer."
            if enhanced
            else "Do not call retrieve_skills. Use only domain tools and your own planning."
        )
        return (
            f"Mode: {mode}\n"
            f"Domain: {domain}\n"
            f"Task: {task}\n"
            f"Context JSON: {json.dumps(context, ensure_ascii=False)}\n"
            f"Expected key steps for evaluation: {expected_text}\n"
            f"{skill_instruction}\n"
            "Use tools rather than only answering from memory. Call the relevant tools in a complete order. "
            "Finish with a short JSON-like summary containing success, used_steps, and final_answer."
        )

    def _system_prompt(self, enhanced: bool) -> str:
        base = (
            "You are an enterprise ReAct agent running inside openJiuwen. "
            "You solve tasks by reasoning, selecting tools, observing results, and then producing a final answer. "
            "Use only registered tools. Keep tool arguments small and valid JSON. "
        )
        if enhanced:
            return (
                base
                + "For every task, retrieve reusable skills before domain execution. "
                + "Treat skills as audited prior experience: follow their steps, note risks, and use rollback guidance."
            )
        return base + "Solve with domain tools only; do not use skill retrieval."

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
