from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from knowledge_agent.tracing.schema import make_id, utc_now_iso


@dataclass
class SkillSpec:
    skill_id: str
    name: str
    domain: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    failure_patterns: list[str] = field(default_factory=list)
    rollback: list[str] = field(default_factory=list)
    evidence_trace_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    version: int = 1
    triggers: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, domain: str, description: str, **kwargs: Any) -> "SkillSpec":
        return cls(
            skill_id=make_id("skill"),
            name=name,
            domain=domain,
            description=description,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillSpec":
        return cls(**data)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

