from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from knowledge_agent.skills.schema import SkillSpec


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str


class SkillGraph:
    """Lightweight in-memory Skill Graph with JSON export."""

    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[GraphEdge] = []
        self.skills: dict[str, SkillSpec] = {}

    @classmethod
    def build_from_skills(cls, skills: list[SkillSpec]) -> "SkillGraph":
        graph = cls()
        for skill in skills:
            graph.add_skill(skill)
        graph._infer_skill_relations()
        return graph

    def add_skill(self, skill: SkillSpec) -> None:
        self.skills[skill.skill_id] = skill
        self.nodes[skill.skill_id] = {
            "id": skill.skill_id,
            "type": "skill",
            "name": skill.name,
            "domain": skill.domain,
            "confidence": skill.confidence,
        }
        domain_id = f"domain:{skill.domain}"
        self.nodes.setdefault(domain_id, {"id": domain_id, "type": "domain", "name": skill.domain})
        self.edges.append(GraphEdge(skill.skill_id, domain_id, "belongs_to"))
        for tool in skill.tools:
            tool_id = f"tool:{tool}"
            self.nodes.setdefault(tool_id, {"id": tool_id, "type": "tool", "name": tool})
            self.edges.append(GraphEdge(skill.skill_id, tool_id, "uses_tool"))
        for pattern in skill.failure_patterns:
            failure_id = f"failure:{self._slug(pattern)}"
            self.nodes.setdefault(
                failure_id,
                {"id": failure_id, "type": "failure_mode", "name": pattern},
            )
            self.edges.append(GraphEdge(skill.skill_id, failure_id, "handles_failure"))

    def retrieve(
        self,
        task: str,
        domain: str,
        context: dict[str, Any] | str | None = None,
        top_k: int = 3,
    ) -> list[SkillSpec]:
        query = self._tokens(task)
        if isinstance(context, dict):
            query |= self._tokens(json.dumps(context, ensure_ascii=False))
        elif context:
            query |= self._tokens(context)
        ranked: list[tuple[float, SkillSpec]] = []
        for skill in self.skills.values():
            if skill.domain != domain:
                continue
            score = self._score(skill, query, domain)
            if score > 0:
                ranked.append((score, skill))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [skill for _, skill in ranked[:top_k]]

    def export_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "nodes": list(self.nodes.values()),
            "edges": [asdict(edge) for edge in self.edges],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes.values()),
            "edges": [asdict(edge) for edge in self.edges],
        }

    def _infer_skill_relations(self) -> None:
        skills = list(self.skills.values())
        for left in skills:
            for right in skills:
                if left.skill_id == right.skill_id:
                    continue
                if left.domain == right.domain and set(left.tools) & set(right.tools):
                    self.edges.append(GraphEdge(left.skill_id, right.skill_id, "alternative_to"))
                if set(left.failure_patterns) & set(right.failure_patterns):
                    self.edges.append(GraphEdge(left.skill_id, right.skill_id, "conflicts_with"))

    def _score(self, skill: SkillSpec, query: set[str], domain: str) -> float:
        skill_tokens = self._tokens(
            " ".join(
                [
                    skill.name,
                    skill.description,
                    " ".join(skill.triggers),
                    " ".join(skill.steps),
                    " ".join(skill.failure_patterns),
                    " ".join(skill.rollback),
                ]
            )
        )
        overlap = len(query & skill_tokens)
        score = overlap * 1.0 + skill.confidence * 2.0
        if skill.domain == domain:
            score += 3.0
        for pattern in skill.failure_patterns:
            if self._tokens(pattern) & query:
                score += 3.0
        for rollback in skill.rollback:
            if self._tokens(rollback) & query:
                score += 1.0
        return score

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower()))

    def _slug(self, text: str) -> str:
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
        return "_".join(tokens[:8]) or "unknown"
