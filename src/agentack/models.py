from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

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


class TraceValidationError(ValueError):
    """Raised when trace input is malformed or unsafe to interpret."""


def _parse_datetime(value: str, field_name: str) -> datetime:
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
        return cls(tool=tool.strip(), operation=operation.strip(), resource=resource, parameters=parameters)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "operation": self.operation,
            "parameters": self.parameters,
        }
        if self.resource is not None:
            payload["resource"] = self.resource
        return payload


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
    approved_action_hash: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None
    line: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, line: int | None = None) -> "TraceEvent":
        if not isinstance(data, dict):
            raise TraceValidationError("trace event must be an object")
        event_type = data.get("type")
        allowed_types = {
            "action_proposed",
            "approval_requested",
            "approval_decision",
            "action_executed",
            "action_blocked",
            "interrupt",
            "session_end",
        }
        if event_type not in allowed_types:
            raise TraceValidationError(f"unsupported event type: {event_type!r}")
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
        approved_action_hash = data.get("approved_action_hash")
        if approved_action_hash is not None:
            if not isinstance(approved_action_hash, str) or len(approved_action_hash) != 64:
                raise TraceValidationError("approved_action_hash must be a 64-character SHA-256 hex string")
            try:
                int(approved_action_hash, 16)
            except ValueError as exc:
                raise TraceValidationError("approved_action_hash must be hexadecimal") from exc
        expires_at_raw = data.get("expires_at")
        expires_at = _parse_datetime(expires_at_raw, "expires_at") if expires_at_raw is not None else None
        reason = data.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise TraceValidationError("reason must be a string or null")

        if event_type in {"action_proposed", "action_executed"}:
            if action_id is None or action is None:
                raise TraceValidationError(f"{event_type} requires action_id and action")
        if event_type in {"approval_requested", "approval_decision"}:
            if action_id is None or approval_id is None:
                raise TraceValidationError(f"{event_type} requires action_id and approval_id")
        if event_type == "approval_decision" and decision is None:
            raise TraceValidationError("approval_decision requires decision")

        return cls(
            type=event_type,
            timestamp=timestamp,
            session_id=session_id.strip(),
            action_id=action_id,
            intent_id=intent_id,
            approval_id=approval_id,
            action=action,
            decision=decision,
            approved_action_hash=approved_action_hash,
            expires_at=expires_at,
            reason=reason,
            line=line,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "session_id": self.session_id,
        }
        for name in ("action_id", "intent_id", "approval_id", "decision", "approved_action_hash", "reason"):
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
    status: Literal["PASS", "FAIL"]
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
