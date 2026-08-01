from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


@dataclass
class Observation:
    content: str
    metrics: dict[str, float] = field(default_factory=dict)
    error_code: str | None = None


@dataclass
class TraceStep:
    step_id: str
    state: str
    plan: str
    action: str
    tool_call: ToolCall | None = None
    observation: Observation | None = None
    reward: float = 0.0
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass
class ExecutionResult:
    success: bool
    score: float
    result: str
    interactions: int
    tool_calls: int
    key_step_f1: float = 0.0
    recovered: bool = False
    failure_reason: str | None = None


@dataclass
class TraceMetadata:
    source: str = "zju_knowledge_agent"
    agent: str = "standalone"
    model: str = "rules"
    timestamp: str = field(default_factory=utc_now_iso)
    audit: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    trace_id: str
    task: str
    domain: str
    steps: list[TraceStep] = field(default_factory=list)
    result: ExecutionResult | None = None
    metadata: TraceMetadata = field(default_factory=TraceMetadata)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        steps = []
        for raw in data.get("steps", []):
            tool = raw.get("tool_call")
            obs = raw.get("observation")
            steps.append(
                TraceStep(
                    step_id=raw["step_id"],
                    state=raw.get("state", ""),
                    plan=raw.get("plan", ""),
                    action=raw.get("action", ""),
                    tool_call=ToolCall(**tool) if tool else None,
                    observation=Observation(**obs) if obs else None,
                    reward=raw.get("reward", 0.0),
                    timestamp=raw.get("timestamp", utc_now_iso()),
                )
            )
        result = data.get("result")
        metadata = data.get("metadata") or {}
        return cls(
            trace_id=data["trace_id"],
            task=data["task"],
            domain=data["domain"],
            steps=steps,
            result=ExecutionResult(**result) if result else None,
            metadata=TraceMetadata(**metadata),
        )

