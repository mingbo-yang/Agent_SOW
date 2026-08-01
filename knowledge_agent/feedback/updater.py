from __future__ import annotations

from knowledge_agent.skills.extractor import SkillExtractor
from knowledge_agent.skills.schema import SkillSpec
from knowledge_agent.skills.store import SkillStore
from knowledge_agent.tracing.schema import Trace


class FeedbackUpdater:
    """Turns online execution results into skill confidence/version updates."""

    def __init__(self, store: SkillStore):
        self.store = store

    def update_from_run(self, trace: Trace, used_skills: list[SkillSpec]) -> None:
        success = bool(trace.result and trace.result.success)
        failure_pattern = trace.result.failure_reason if trace.result else None
        if used_skills:
            for skill in used_skills:
                self.store.update_feedback(
                    skill.skill_id,
                    success=success,
                    trace_id=trace.trace_id,
                    failure_pattern=failure_pattern,
                )
            return
        if success:
            for skill in SkillExtractor().extract_from_traces([trace]):
                self.store.save(skill)

