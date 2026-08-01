from __future__ import annotations

import re
from collections import defaultdict

from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.tracing.schema import Trace

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "请",
    "一个",
    "进行",
    "任务",
}


class SkillExtractor:
    """Rule-first trajectory-to-skill extractor with an optional LLM hook.

    The MVP keeps the default path deterministic and offline. A caller can
    subclass ``extract_with_llm`` later without changing downstream interfaces.
    """

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm

    def extract_from_traces(self, traces: list[Trace]) -> list[SkillSpec]:
        if self.use_llm:
            return self.extract_with_llm(traces)
        return self.extract_with_rules(traces)

    def extract_with_llm(self, traces: list[Trace]) -> list[SkillSpec]:
        return self.extract_with_rules(traces)

    def extract_with_rules(self, traces: list[Trace]) -> list[SkillSpec]:
        grouped: dict[tuple[str, str], list[Trace]] = defaultdict(list)
        for trace in traces:
            grouped[(trace.domain, self._intent_key(trace.task))].append(trace)

        skills: list[SkillSpec] = []
        for (domain, intent), group in grouped.items():
            success_traces = [t for t in group if t.result and t.result.success]
            failure_traces = [t for t in group if t.result and not t.result.success]
            source = success_traces[0] if success_traces else group[0]

            steps = self._stable_actions(success_traces or group)
            tools = self._stable_tools(group)
            failures = self._failure_patterns(failure_traces)
            rollback = self._rollback_steps(group, failures)
            triggers = sorted(set(self._keywords(" ".join(t.task for t in group)) + [domain, intent]))
            confidence = self._confidence(success_traces, failure_traces, group)
            name = f"{domain}_{intent}_skill"
            description = f"Reusable {domain} skill for {intent.replace('_', ' ')} tasks."
            skills.append(
                SkillSpec.create(
                    name=name,
                    domain=domain,
                    description=description,
                    preconditions=self._preconditions(source),
                    inputs=["task", "context"],
                    outputs=["decision", "evidence", "trace"],
                    tools=tools,
                    steps=steps,
                    failure_patterns=failures,
                    rollback=rollback,
                    evidence_trace_ids=[t.trace_id for t in group],
                    confidence=confidence,
                    triggers=triggers,
                    metadata={
                        "source": "rule_extractor",
                        "success_traces": len(success_traces),
                        "failure_traces": len(failure_traces),
                    },
                )
            )
        return self._deduplicate(skills)

    def _intent_key(self, task: str) -> str:
        keywords = self._keywords(task)
        return "_".join(keywords[:3]) if keywords else "general"

    def _keywords(self, text: str) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower())
        cleaned = [w for w in words if w not in STOPWORDS and len(w) > 1]
        seen: set[str] = set()
        result = []
        for word in cleaned:
            if word not in seen:
                result.append(word)
                seen.add(word)
        return result

    def _stable_actions(self, traces: list[Trace]) -> list[str]:
        actions = []
        for trace in traces:
            for step in trace.steps:
                if step.action and step.action not in actions:
                    actions.append(step.action)
        return actions[:8]

    def _stable_tools(self, traces: list[Trace]) -> list[str]:
        tools = []
        for trace in traces:
            for step in trace.steps:
                if step.tool_call and step.tool_call.name not in tools:
                    tools.append(step.tool_call.name)
        return tools

    def _failure_patterns(self, traces: list[Trace]) -> list[str]:
        patterns = []
        for trace in traces:
            if trace.result and trace.result.failure_reason:
                patterns.append(trace.result.failure_reason)
            for step in trace.steps:
                if step.tool_call and step.tool_call.error:
                    patterns.append(step.tool_call.error)
        return sorted(set(patterns))

    def _rollback_steps(self, traces: list[Trace], failures: list[str]) -> list[str]:
        rollback = []
        for trace in traces:
            for step in trace.steps:
                text = f"{step.action} {step.plan}".lower()
                if "rollback" in text or "recover" in text or "补救" in text or "回退" in text:
                    rollback.append(step.action)
        if not rollback and failures:
            rollback = ["validate_inputs", "select_alternative_tool", "retry_with_constraints"]
        return sorted(set(rollback))

    def _preconditions(self, trace: Trace) -> list[str]:
        preconditions = ["task_goal_is_clear"]
        if "permission" in trace.task.lower() or "权限" in trace.task:
            preconditions.append("permission_context_available")
        if "policy" in trace.task.lower() or "合规" in trace.task or "规则" in trace.task:
            preconditions.append("policy_context_available")
        return preconditions

    def _confidence(self, success: list[Trace], failure: list[Trace], group: list[Trace]) -> float:
        if not group:
            return 0.5
        success_rate = len(success) / len(group)
        evidence_bonus = min(len(group), 5) * 0.04
        recovery_bonus = 0.08 if failure and success else 0.0
        return round(min(0.95, 0.35 + success_rate * 0.45 + evidence_bonus + recovery_bonus), 3)

    def _deduplicate(self, skills: list[SkillSpec]) -> list[SkillSpec]:
        merged: dict[tuple[str, tuple[str, ...]], SkillSpec] = {}
        for skill in skills:
            key = (skill.domain, tuple(sorted(skill.tools)))
            current = merged.get(key)
            if current is None:
                merged[key] = skill
                continue
            current.steps = self._union(current.steps, skill.steps)
            current.failure_patterns = self._union(current.failure_patterns, skill.failure_patterns)
            current.rollback = self._union(current.rollback, skill.rollback)
            current.evidence_trace_ids = self._union(
                current.evidence_trace_ids, skill.evidence_trace_ids
            )
            current.triggers = self._union(current.triggers, skill.triggers)
            current.confidence = round(max(current.confidence, skill.confidence), 3)
            current.version += 1
            current.touch()
        return list(merged.values())

    def _union(self, left: list[str], right: list[str]) -> list[str]:
        result = list(left)
        for item in right:
            if item not in result:
                result.append(item)
        return result

