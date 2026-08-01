from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    observation: str
    error: str | None = None


class MockToolRegistry:
    """Deterministic tool registry used by demos and evaluation."""

    DEFAULT_TOOLS = {
        "literature_search",
        "paper_reader",
        "schema_validator",
        "protocol_designer",
        "constraint_checker",
        "report_writer",
        "document_parser",
        "policy_checker",
        "risk_scanner",
        "evidence_collector",
        "decision_engine",
        "monitoring_reader",
        "log_search",
        "diagnosis_engine",
        "runbook_selector",
        "health_checker",
        "tool_router",
        "human_review",
    }

    def __init__(self, tools: set[str] | None = None):
        self.tools = tools or set(self.DEFAULT_TOOLS)

    def execute(self, tool_name: str, args: dict[str, Any] | None = None) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(False, "", f"tool_unavailable:{tool_name}")
        args = args or {}
        return ToolResult(True, f"{tool_name} completed for {args.get('step', 'step')}")

