from __future__ import annotations

import json
from pathlib import Path

from knowledge_agent.skills.schema import SkillSpec


class SkillStore:
    """JSON-backed skill store with simple versioned feedback updates."""

    def __init__(self, path: str | Path = "outputs/skills.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, SkillSpec] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._skills = {}
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._skills = {item["skill_id"]: SkillSpec.from_dict(item) for item in data}

    def flush(self) -> None:
        data = [skill.to_dict() for skill in self.list()]
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def save(self, skill: SkillSpec) -> SkillSpec:
        existing = self._find_merge_target(skill)
        if existing:
            self._merge(existing, skill)
            skill = existing
        self._skills[skill.skill_id] = skill
        self.flush()
        return skill

    def save_many(self, skills: list[SkillSpec]) -> list[SkillSpec]:
        saved = [self.save(skill) for skill in skills]
        self.flush()
        return saved

    def list(self) -> list[SkillSpec]:
        return sorted(self._skills.values(), key=lambda s: (s.domain, s.name))

    def get(self, skill_id: str) -> SkillSpec | None:
        return self._skills.get(skill_id)

    def update_feedback(
        self,
        skill_id: str,
        success: bool,
        trace_id: str | None = None,
        failure_pattern: str | None = None,
    ) -> None:
        skill = self._skills.get(skill_id)
        if skill is None:
            return
        delta = 0.06 if success else -0.08
        skill.confidence = round(min(0.99, max(0.05, skill.confidence + delta)), 3)
        if trace_id and trace_id not in skill.evidence_trace_ids:
            skill.evidence_trace_ids.append(trace_id)
        if failure_pattern and failure_pattern not in skill.failure_patterns:
            skill.failure_patterns.append(failure_pattern)
        skill.version += 1
        skill.touch()
        self.flush()

    def _find_merge_target(self, skill: SkillSpec) -> SkillSpec | None:
        skill_tools = set(skill.tools)
        skill_triggers = set(skill.triggers)
        for current in self._skills.values():
            if current.skill_id == skill.skill_id:
                return current
            if current.domain != skill.domain:
                continue
            tool_overlap = len(skill_tools & set(current.tools))
            trigger_overlap = len(skill_triggers & set(current.triggers))
            if tool_overlap >= max(1, min(len(skill_tools), len(current.tools))) and trigger_overlap >= 2:
                return current
        return None

    def _merge(self, target: SkillSpec, incoming: SkillSpec) -> None:
        for attr in ["preconditions", "inputs", "outputs", "tools", "steps", "failure_patterns", "rollback", "evidence_trace_ids", "triggers"]:
            values = getattr(target, attr)
            for item in getattr(incoming, attr):
                if item not in values:
                    values.append(item)
        target.confidence = round(max(target.confidence, incoming.confidence), 3)
        target.version += 1
        target.touch()

