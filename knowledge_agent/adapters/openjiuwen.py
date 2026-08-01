from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from knowledge_agent.graph.skill_graph import SkillGraph
from knowledge_agent.planner.agent import AgentRunResult, KnowledgeEnhancedAgent
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.schema import (
    ExecutionResult,
    Observation,
    ToolCall,
    Trace,
    TraceMetadata,
    TraceStep,
    make_id,
)


@dataclass
class OpenJiuwenRuntimeAdapter:
    """Optional adapter for openJiuwen Agent/Core runtimes.

    The project remains runnable without openJiuwen. When the ``openjiuwen``
    package is installed, this adapter provides conversion utilities and a
    wrapper interface that lets openJiuwen-collected trajectories feed the
    same Trace -> Skill -> SkillGraph -> Feedback loop used by the standalone
    demos.
    """

    skill_store: SkillStore
    skill_graph: SkillGraph

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("openjiuwen") is not None

    def require_available(self) -> None:
        if not self.is_available():
            raise RuntimeError(
                "openjiuwen is not installed. Install it with `pip install -U openjiuwen` "
                "or run the standalone demos/evaluation."
            )

    def convert_run_to_trace(
        self,
        run_payload: dict[str, Any],
        task: str,
        domain: str,
        success: bool,
        score: float = 1.0,
    ) -> Trace:
        """Convert a generic openJiuwen run payload into the local Trace schema.

        The converter accepts the common event-like shape used by workflow and
        ReAct systems: each step/event can expose ``state``, ``plan``, ``action``,
        ``tool_name``, ``tool_args``, ``observation``, and ``error``. Unknown
        fields are ignored and retained only through the audit metadata.
        """

        steps = []
        for raw in run_payload.get("steps", run_payload.get("events", [])):
            tool_name = raw.get("tool_name") or raw.get("tool")
            error = raw.get("error")
            observation = raw.get("observation_obj")
            if observation is None:
                observation = Observation(content=str(raw.get("observation", "")), error_code=error)
            elif isinstance(observation, dict):
                observation = Observation(
                    content=str(observation.get("content", "")),
                    metrics=observation.get("metrics", {}) or {},
                    error_code=observation.get("error_code", error),
                )
            steps.append(
                TraceStep(
                    step_id=raw.get("step_id", make_id("ojw_step")),
                    state=str(raw.get("state", "")),
                    plan=str(raw.get("plan", raw.get("thought", ""))),
                    action=str(raw.get("action", raw.get("component", ""))),
                    tool_call=ToolCall(
                        name=str(tool_name),
                        args=raw.get("tool_args", raw.get("args", {})) or {},
                        success=error is None,
                        error=error,
                    )
                    if tool_name
                    else None,
                    observation=observation,
                    reward=float(raw.get("reward", 1.0 if error is None else -1.0)),
                    timestamp=str(raw.get("timestamp", "")) or TraceMetadata().timestamp,
                )
            )
        return Trace(
            trace_id=run_payload.get("trace_id", make_id("ojw_trace")),
            task=task,
            domain=domain,
            steps=steps,
            result=ExecutionResult(
                success=success,
                score=score,
                result=str(run_payload.get("result", "openjiuwen_run")),
                interactions=len(steps),
                tool_calls=sum(1 for step in steps if step.tool_call is not None),
                key_step_f1=float(run_payload.get("key_step_f1", 0.0)),
                recovered=bool(run_payload.get("recovered", False)),
                failure_reason=run_payload.get("failure_reason"),
            ),
            metadata=TraceMetadata(
                source="openjiuwen",
                agent=str(run_payload.get("agent", "openjiuwen")),
                audit=run_payload.get("audit", {}),
            ),
        )

    def register_skill_as_openjiuwen_payload(self, skill: SkillSpec) -> dict[str, Any]:
        """Return a framework-friendly skill payload for openJiuwen skill stores."""

        return {
            "id": skill.skill_id,
            "name": skill.name,
            "domain": skill.domain,
            "description": skill.description,
            "triggers": skill.triggers,
            "content": "\n".join(
                [
                    "## Preconditions",
                    *[f"- {item}" for item in skill.preconditions],
                    "## Steps",
                    *[f"- {item}" for item in skill.steps],
                    "## Failure Patterns",
                    *[f"- {item}" for item in skill.failure_patterns],
                    "## Rollback",
                    *[f"- {item}" for item in skill.rollback],
                ]
            ),
            "metadata": {
                "confidence": skill.confidence,
                "version": skill.version,
                "evidence_trace_ids": skill.evidence_trace_ids,
                "tools": skill.tools,
            },
        }

    def make_enhanced_agent(self) -> KnowledgeEnhancedAgent:
        """Create the local enhanced agent over skills collected from openJiuwen."""

        return KnowledgeEnhancedAgent(self.skill_graph, skill_store=self.skill_store)
