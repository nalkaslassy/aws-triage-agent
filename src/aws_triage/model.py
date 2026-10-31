"""Small, serializable contracts shared by collectors and investigation logic."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def utc_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return result


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    resource: str
    source: str
    status: str
    data: dict[str, Any]
    collected_at: str

    def __post_init__(self):
        if self.status not in {"observed", "unavailable", "partial", "not_collected"}:
            raise ValueError(f"Invalid evidence status: {self.status}")
        utc_time(self.collected_at)


@dataclass
class Bundle:
    application: str
    start: str
    end: str
    evidence: list[Evidence]
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("Unsupported bundle schema version")
        if utc_time(self.start) >= utc_time(self.end):
            raise ValueError("Investigation start must precede end")
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique")

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, "evidence": [Evidence(**e) for e in value["evidence"]]})

    def to_dict(self):
        return asdict(self)


@dataclass
class Finding:
    title: str
    classification: str
    explanation: str
    evidence_ids: list[str]
    next_steps: list[str]
    owner: str


@dataclass
class Report:
    application: str
    start: str
    end: str
    findings: list[Finding] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
