from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_agent.tracing.schema import (
    ExecutionResult,
    Observation,
    ToolCall,
    Trace,
    TraceMetadata,
    TraceStep,
    make_id,
)


class TraceRecorder:
    """Records one Agent run and persists it as JSON and JSONL."""

    def __init__(self, base_dir: str | Path = "outputs/traces"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._current: Trace | None = None

    def start(self, task: str, domain: str) -> str:
        trace_id = make_id("trace")
        self._current = Trace(
            trace_id=trace_id,
            task=task,
            domain=domain,
            metadata=TraceMetadata(),
        )
        return trace_id

    def record_step(
        self,
        state: str,
        plan: str,
        action: str,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        observation: str | None = None,
        error: str | None = None,
        reward: float = 0.0,
    ) -> None:
        if self._current is None:
            raise RuntimeError("TraceRecorder.start() must be called before record_step().")
        tool_call = None
        if tool_name:
            tool_call = ToolCall(
                name=tool_name,
                args=tool_args or {},
                success=error is None,
                error=error,
            )
        obs = Observation(content=observation or "", error_code=error)
        self._current.steps.append(
            TraceStep(
                step_id=make_id("step"),
                state=state,
                plan=plan,
                action=action,
                tool_call=tool_call,
                observation=obs,
                reward=reward,
            )
        )

    def update_metadata(
        self,
        agent: str | None = None,
        model: str | None = None,
        audit: dict[str, Any] | None = None,
    ) -> None:
        if self._current is None:
            raise RuntimeError("TraceRecorder.start() must be called before update_metadata().")
        if agent is not None:
            self._current.metadata.agent = agent
        if model is not None:
            self._current.metadata.model = model
        if audit:
            self._current.metadata.audit.update(audit)

    def finish(
        self,
        success: bool,
        score: float,
        result: str,
        key_step_f1: float = 0.0,
        recovered: bool = False,
        failure_reason: str | None = None,
    ) -> Trace:
        if self._current is None:
            raise RuntimeError("TraceRecorder.start() must be called before finish().")
        tool_calls = sum(1 for step in self._current.steps if step.tool_call is not None)
        self._current.result = ExecutionResult(
            success=success,
            score=score,
            result=result,
            interactions=len(self._current.steps),
            tool_calls=tool_calls,
            key_step_f1=key_step_f1,
            recovered=recovered,
            failure_reason=failure_reason,
        )
        trace = self._current
        self._persist(trace)
        self._current = None
        return trace

    def _persist(self, trace: Trace) -> None:
        data = trace.to_dict()
        (self.base_dir / f"{trace.trace_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        with (self.base_dir / "traces.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_traces_jsonl(path: str | Path) -> list[Trace]:
    path = Path(path)
    if not path.exists():
        return []
    traces = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            traces.append(Trace.from_dict(json.loads(line)))
    return traces
