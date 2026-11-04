"""Shared, bounded input contract for files, recording and the public API."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import Action, TraceEvent, TraceValidationError

MAX_LINE_BYTES = 1_000_000
MAX_TRACE_BYTES = 32_000_000
MAX_EVENTS = 100_000
MAX_JSON_DEPTH = 64


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TraceValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise TraceValidationError(f"non-finite JSON number: {value}")


def strict_json_loads(raw: str | bytes, *, max_bytes: int = MAX_LINE_BYTES) -> Any:
    """Reject excessive nesting before the JSON decoder allocates nested objects."""
    try:
        if isinstance(raw, bytes):
            if len(raw) > max_bytes:
                raise TraceValidationError(f"JSON exceeds {max_bytes} bytes")
            text = raw.decode("utf-8")
        elif isinstance(raw, str):
            if len(raw.encode("utf-8")) > max_bytes:
                raise TraceValidationError(f"JSON exceeds {max_bytes} bytes")
            text = raw
        else:
            raise TraceValidationError("JSON input must be text or bytes")
    except UnicodeError as exc:
        raise TraceValidationError("JSON input is not valid UTF-8") from exc
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise TraceValidationError("JSON exceeds maximum nesting depth")
        elif char in "]}":
            depth -= 1
    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise TraceValidationError(f"invalid JSON: {exc}") from exc


def validate_action(action: Action) -> Action:
    if not isinstance(action, Action):
        raise TraceValidationError("action must be an Action instance")
    return Action.from_dict(action.to_dict())


def _datetime_text(value: object, name: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TraceValidationError(f"{name} must be a timezone-aware datetime")
    return value.isoformat()


def validate_event(event: TraceEvent) -> TraceEvent:
    if not isinstance(event, TraceEvent):
        raise TraceValidationError("events must contain TraceEvent instances")
    if event.line is not None and (type(event.line) is not int or event.line < 1):
        raise TraceValidationError("event line must be a positive integer or null")
    payload: dict[str, Any] = {
        "schema_version": event.schema_version,
        "type": event.type,
        "timestamp": _datetime_text(event.timestamp, "timestamp"),
        "session_id": event.session_id,
    }
    for name in ("action_id", "intent_id", "approval_id", "decision", "reason"):
        value = getattr(event, name)
        if value is not None:
            payload[name] = value
    if event.action is not None:
        payload["action"] = validate_action(event.action).to_dict()
    if event.expires_at is not None:
        payload["expires_at"] = _datetime_text(event.expires_at, "expires_at")
    normalized = TraceEvent.from_dict(payload, line=event.line)
    try:
        encoded = json.dumps(normalized.to_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, OverflowError) as exc:
        raise TraceValidationError("event is not safely serializable JSON") from exc
    if len(encoded) > MAX_LINE_BYTES:
        raise TraceValidationError(f"event exceeds {MAX_LINE_BYTES} bytes")
    return normalized


def validate_events(events: list[TraceEvent], *, max_events: int = MAX_EVENTS) -> list[TraceEvent]:
    if not isinstance(events, list) or not events:
        raise TraceValidationError("trace contains no events or is not a list")
    if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
        raise TraceValidationError(f"max_events must be from 1 to {MAX_EVENTS}")
    if len(events) > max_events:
        raise TraceValidationError(f"trace exceeds maximum event count {max_events}")
    normalized: list[TraceEvent] = []
    total_bytes = 0
    for event in events:
        item = validate_event(event)
        total_bytes += len(json.dumps(item.to_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8")) + 1
        if total_bytes > MAX_TRACE_BYTES:
            raise TraceValidationError(f"trace exceeds {MAX_TRACE_BYTES} bytes")
        normalized.append(item)
    if len({event.session_id for event in normalized}) != 1:
        raise TraceValidationError("one trace must contain exactly one session_id")
    return normalized
