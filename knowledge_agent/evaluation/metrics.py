from __future__ import annotations

from statistics import mean
from typing import Any

from knowledge_agent.evaluation.result import AgentRunResult


def aggregate_results(results: list[AgentRunResult]) -> dict[str, Any]:
    if not results:
        return {
            "num_tasks": 0,
            "success_rate": 0.0,
            "avg_score": 0.0,
            "avg_key_step_f1": 0.0,
            "avg_interactions": 0.0,
            "avg_tool_calls": 0.0,
            "recovery_rate": 0.0,
        }
    return {
        "num_tasks": len(results),
        "success_rate": round(mean(1.0 if r.success else 0.0 for r in results), 3),
        "avg_score": round(mean(r.score for r in results), 3),
        "avg_key_step_f1": round(mean(r.key_step_f1 for r in results), 3),
        "avg_interactions": round(mean(r.interactions for r in results), 3),
        "avg_tool_calls": round(mean(r.tool_calls for r in results), 3),
        "recovery_rate": round(mean(1.0 if r.recovered else 0.0 for r in results), 3),
    }


def compare_reports(baseline: dict[str, Any], enhanced: dict[str, Any]) -> dict[str, Any]:
    return {
        "success_rate_delta": round(enhanced["success_rate"] - baseline["success_rate"], 3),
        "key_step_f1_delta": round(enhanced["avg_key_step_f1"] - baseline["avg_key_step_f1"], 3),
        "interaction_delta": round(enhanced["avg_interactions"] - baseline["avg_interactions"], 3),
        "tool_call_delta": round(enhanced["avg_tool_calls"] - baseline["avg_tool_calls"], 3),
        "recovery_rate_delta": round(enhanced["recovery_rate"] - baseline["recovery_rate"], 3),
    }
