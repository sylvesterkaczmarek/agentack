from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TRACE_SCHEMA_VERSION = 2

EventType = Literal[
    "action_proposed",
    "approval_requested",
    "approval_decision",
    "action_executed",
    "action_blocked",
    "interrupt",
    "session_end",
]
Decision = Literal["allow", "deny"]
Severity = Literal["low", "medium", "high", "critical"]
EvaluationStatus = Literal["PASS", "FAIL", "INCOMPLETE"]


class TraceValidationError(ValueError):
    """Raised when trace input is malformed or unsafe to interpret."""


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TraceValidationError(f"{field_name} must be a non-empty ISO-8601 string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TraceValidationError(f"{field_name} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise TraceValidationError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 20:
        raise TraceValidationError("action parameters exceed maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise TraceValidationError("action parameters cannot contain NaN or Infinity")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TraceValidationError("action parameter keys must be strings")
            _validate_json_value(item, depth=depth + 1)
        return
    raise TraceValidationError(f"unsupported action parameter type: {type(value).__name__}")


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str], *, context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise TraceValidationError(f"{context} contains unknown field(s): {', '.join(unknown)}")


@dataclass(frozen=True)
class Action:
    tool: str
    operation: str
    resource: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        if not isinstance(data, dict):
            raise TraceValidationError("action must be an object")
        _reject_unknown_fields(
            data,
            {"tool", "operation", "resource", "parameters"},
            context="action",
        )
        tool = data.get("tool")
        operation = data.get("operation")
        resource = data.get("resource")
        parameters = data.get("parameters", {})
        if not isinstance(tool, str) or not tool.strip():
            raise TraceValidationError("action.tool must be a non-empty string")
        if not isinstance(operation, str) or not operation.strip():
            raise TraceValidationError("action.operation must be a non-empty string")
        if resource is not None and not isinstance(resource, str):
            raise TraceValidationError("action.resource must be a string or null")
        if not isinstance(parameters, dict):
            raise TraceValidationError("action.parameters must be an object")
        _validate_json_value(parameters)
        return cls(
            tool=tool.strip(),
            operation=operation.strip(),
            resource=resource,
            parameters=parameters,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "operation": self.operation,
            "parameters": self.parameters,
        }
        if self.resource is not None:
            payload["resource"] = self.resource
        return payload


_EVENT_FIELDS: dict[str, set[str]] = {
    "action_proposed": {
        "schema_version", "type", "timestamp", "session_id", "action_id", "intent_id", "action"
    },
    "approval_requested": {
        "schema_version", "type", "timestamp", "session_id", "action_id", "intent_id", "approval_id", "action"
    },
    "approval_decision": {
        "schema_version", "type", "timestamp", "session_id", "action_id", "intent_id", "approval_id", "decision", "expires_at"
    },
    "action_executed": {
        "schema_version", "type", "timestamp", "session_id", "action_id", "intent_id", "approval_id", "action"
    },
    "action_blocked": {
        "schema_version", "type", "timestamp", "session_id", "action_id", "intent_id", "approval_id", "reason"
    },
    "interrupt": {"schema_version", "type", "timestamp", "session_id", "reason"},
    "session_end": {"schema_version", "type", "timestamp", "session_id", "reason"},
}


@dataclass(frozen=True)
class TraceEvent:
    type: EventType
    timestamp: datetime
    session_id: str
    action_id: str | None = None
    intent_id: str | None = None
    approval_id: str | None = None
    action: Action | None = None
    decision: Decision | None = None
    expires_at: datetime | None = None
    reason: str | None = None
    line: int | None = None
    schema_version: int = TRACE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, line: int | None = None) -> "TraceEvent":
        if not isinstance(data, dict):
            raise TraceValidationError("trace event must be an object")

        schema_version = data.get("schema_version")
        if schema_version != TRACE_SCHEMA_VERSION:
            raise TraceValidationError(
                f"schema_version must be {TRACE_SCHEMA_VERSION}; got {schema_version!r}"
            )

        event_type = data.get("type")
        if event_type not in _EVENT_FIELDS:
            raise TraceValidationError(f"unsupported event type: {event_type!r}")
        _reject_unknown_fields(data, _EVENT_FIELDS[event_type], context=str(event_type))

        timestamp = _parse_datetime(data.get("timestamp"), "timestamp")
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise TraceValidationError("session_id must be a non-empty string")

        action_id = data.get("action_id")
        intent_id = data.get("intent_id")
        approval_id = data.get("approval_id")
        for name, value in (("action_id", action_id), ("intent_id", intent_id), ("approval_id", approval_id)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise TraceValidationError(f"{name} must be a non-empty string or null")

        action_data = data.get("action")
        action = Action.from_dict(action_data) if action_data is not None else None
        decision = data.get("decision")
        if decision is not None and decision not in {"allow", "deny"}:
            raise TraceValidationError("decision must be 'allow' or 'deny'")
        expires_at_raw = data.get("expires_at")
        expires_at = _parse_datetime(expires_at_raw, "expires_at") if expires_at_raw is not None else None
        reason = data.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise TraceValidationError("reason must be a string or null")

        if event_type in {"action_proposed", "approval_requested", "action_executed"}:
            if action_id is None or action is None:
                raise TraceValidationError(f"{event_type} requires action_id and action")
        if event_type in {"approval_requested", "approval_decision"} and approval_id is None:
            raise TraceValidationError(f"{event_type} requires approval_id")
        if event_type in {"approval_requested", "approval_decision", "action_blocked"} and action_id is None:
            raise TraceValidationError(f"{event_type} requires action_id")
        if event_type == "approval_decision" and decision is None:
            raise TraceValidationError("approval_decision requires decision")

        return cls(
            type=event_type,  # type: ignore[arg-type]
            timestamp=timestamp,
            session_id=session_id.strip(),
            action_id=action_id,
            intent_id=intent_id,
            approval_id=approval_id,
            action=action,
            decision=decision,  # type: ignore[arg-type]
            expires_at=expires_at,
            reason=reason,
            line=line,
            schema_version=schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": self.type,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "session_id": self.session_id,
        }
        for name in ("action_id", "intent_id", "approval_id", "decision", "reason"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        if self.action is not None:
            result["action"] = self.action.to_dict()
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return result


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    title: str
    message: str
    line: int | None = None
    action_id: str | None = None
    approval_id: str | None = None
    standards: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["standards"] = list(self.standards)
        return payload


@dataclass(frozen=True)
class EvaluationReport:
    status: EvaluationStatus
    events: int
    findings: tuple[Finding, ...]
    rule_counts: dict[str, int]
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "source": self.source,
            "events": self.events,
            "finding_count": len(self.findings),
            "rule_counts": self.rule_counts,
            "findings": [finding.to_dict() for finding in self.findings],
        }
