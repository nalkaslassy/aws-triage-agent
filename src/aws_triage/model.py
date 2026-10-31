"""Small, serializable contracts shared by collectors and investigation logic."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
import re
from typing import Any
from urllib.parse import urlsplit


def utc_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return result


def text_field(value, label, maximum=1024):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be nonempty text (maximum {maximum} characters)")


def number(value, label, integer=False):
    if value is None:
        return
    if type(value) not in ((int,) if integer else (int, float)) or value < 0 or value > 1e18 or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite nonnegative {'integer' if integer else 'number'} or null")


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    resource: str
    source: str
    status: str
    data: dict[str, Any]
    collected_at: str
    source_url: str | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", self.id):
            raise ValueError("Invalid evidence ID")
        for label in ("kind", "resource", "source"):
            text_field(getattr(self, label), label)
        if self.status not in {"observed", "unavailable", "partial", "not_collected"}:
            raise ValueError(f"Invalid evidence status: {self.status}")
        utc_time(self.collected_at)
        if not isinstance(self.data, dict):
            raise ValueError("Evidence data must be an object")
        if "reason" in self.data and (not isinstance(self.data["reason"], str) or len(self.data["reason"]) > 4096):
            raise ValueError("Evidence reason must be text")
        if self.kind in {"lambda_metrics", "api_metrics"}:
            fields = ("Errors", "Invocations", "Throttles") if self.kind == "lambda_metrics" else (
                "requests", "server_errors", "client_errors", "latency_ms", "integration_latency_ms")
            for key in fields:
                number(self.data.get(key), key)
        if self.kind == "api_metrics":
            if self.data.get("window") not in {"incident", "baseline"}:
                raise ValueError("API metric window must be incident or baseline")
            if utc_time(self.data.get("start")) >= utc_time(self.data.get("end")):
                raise ValueError("Invalid API metric window")
        if self.kind == "lambda_concurrency":
            number(self.data.get("reserved_concurrency"), "reserved_concurrency", integer=True)
        if self.kind == "lambda_configuration":
            for key in ("orders_table", "expected_table"):
                value = self.data.get(key)
                if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", value)):
                    raise ValueError(f"Invalid {key}")
            for key in ("Role", "FunctionArn", "LastModified", "RevisionId", "CodeSha256", "State", "LastUpdateStatus"):
                if self.data.get(key) is not None:
                    text_field(self.data[key], key)
        if self.kind == "permission_simulation":
            if self.data.get("decision") is not None and self.data["decision"] not in {"allowed", "explicitDeny", "implicitDeny"}:
                raise ValueError("Invalid simulation decision")
            for key in ("role", "action", "target"):
                if self.data.get(key) is not None:
                    text_field(self.data[key], key)
            context = self.data.get("missing_context", [])
            if not isinstance(context, list) or len(context) > 20 or any(not isinstance(k, str) or len(k) > 256 for k in context):
                raise ValueError("Invalid simulation context")
        if self.kind == "change_history":
            events = self.data.get("events", [])
            if not isinstance(events, list) or len(events) > 10:
                raise ValueError("Invalid change history")
            for event in events:
                if not isinstance(event, dict) or set(event) != {"EventId", "EventName", "EventSource", "EventTime"}:
                    raise ValueError("Invalid change event")
                for key, value in event.items():
                    text_field(value, key, 256)
                utc_time(event["EventTime"])
        if self.kind == "log_signals":
            for key in ("access_denied", "timeout", "exception", "resource_missing", "unverified_mentions"):
                number(self.data.get(key), key, integer=True)
            samples = self.data.get("samples", [])
            if "function_name" in self.data:
                text_field(self.data["function_name"], "function_name", 64)
            if not isinstance(samples, list) or len(samples) > 20 or any(not isinstance(s, dict) for s in samples):
                raise ValueError("Log samples must be at most twenty objects")
            for sample in samples:
                number(sample.get("timestamp"), "sample timestamp", integer=True)
                for key, value in sample.items():
                    if key != "timestamp" and (not isinstance(value, (str, type(None))) or isinstance(value, str) and len(value) > 1024):
                        raise ValueError("Log sample fields must be bounded text")
        if self.source_url is not None:
            text_field(self.source_url, "source_url", 2048)
            url = urlsplit(self.source_url)
            if (url.scheme != "https" or url.username or url.password or url.port
                or not re.fullmatch(r"(?:[a-z0-9-]+\.)?console\.aws\.amazon\.com", url.hostname or "")
                or re.search(r"[\s<>]", self.source_url)):
                raise ValueError("Evidence links must be HTTPS AWS console URLs")


@dataclass
class Bundle:
    application: str
    start: str
    end: str
    evidence: list[Evidence]
    schema_version: int = 1

    def __post_init__(self):
        text_field(self.application, "application")
        if not isinstance(self.evidence, list) or len(self.evidence) > 1000 or any(not isinstance(e, Evidence) for e in self.evidence):
            raise ValueError("Bundle evidence must be at most one thousand Evidence objects")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported bundle schema version")
        if utc_time(self.start) >= utc_time(self.end):
            raise ValueError("Investigation start must precede end")
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("evidence"), list):
            raise ValueError("Bundle must contain an evidence array")
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
    resource: str = ""


@dataclass
class Report:
    application: str
    start: str
    end: str
    findings: list[Finding] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "first-pass"

    def to_dict(self):
        return asdict(self)
