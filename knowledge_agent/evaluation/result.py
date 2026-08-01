from __future__ import annotations

from dataclasses import dataclass, field

from knowledge_agent.tracing.schema import Trace


@dataclass
class AgentRunResult:
    task: str
    domain: str
    success: bool
    score: float
    plan: list[str]
    agent_type: str = "enhanced"
    task_id: str | None = None
    selected_skills: list[str] = field(default_factory=list)
    interactions: int = 0
    tool_calls: int = 0
    key_step_f1: float = 0.0
    recovered: bool = False
    trace: Trace | None = None
    failure_reason: str | None = None
    failure_detected: bool = False
    matched_failure_patterns: list[str] = field(default_factory=list)
    rollback_used: bool = False
    recovery_success: bool = False
    required_order_ok: bool = True
    latency_ms: int = 0


def key_step_f1_score(predicted: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    predicted_set = set(predicted)
    expected_set = set(expected)
    true_positive = len(predicted_set & expected_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(expected_set)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 3)
