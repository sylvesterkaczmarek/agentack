from __future__ import annotations

import base64
import binascii
import math
import re
import secrets
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..models import TraceValidationError
from ..validation import strict_json_loads

_MAX_REQUEST_BYTES = 5_000_000
_MAX_PAYLOADS = 100
_MAX_TOTAL_BYTES = 16_000_000


@dataclass(frozen=True)
class ToolDecision:
    tool_use_id: str
    tool_name: str | None
    decision: str
    source: str | None
    session_id: str | None = None


_VALUE_FIELDS = {"stringValue", "boolValue", "intValue", "doubleValue", "bytesValue", "arrayValue", "kvlistValue"}
_DECISION_EVENTS = {"tool_decision", "claude_code.tool_decision"}


def _otel_value(value: Any, *, depth: int = 0) -> Any:
    """Decode the supported OTLP AnyValue union without coercing ambiguous input.

    Unknown message fields are ignored, as OTLP requires. An empty AnyValue is
    permitted, but cannot supply a required security-relevant string attribute.
    """
    if depth > 20 or not isinstance(value, dict):
        raise TraceValidationError("OTLP AnyValue must be a bounded typed object")
    fields = _VALUE_FIELDS.intersection(value)
    if len(fields) > 1:
        raise TraceValidationError("OTLP AnyValue contains multiple value alternatives")
    if not fields:
        return None
    field = next(iter(fields))
    item = value[field]
    if field == "stringValue":
        if not isinstance(item, str):
            raise TraceValidationError("OTLP stringValue must be a string")
        try:
            item.encode("utf-8")
        except UnicodeError as exc:
            raise TraceValidationError("OTLP stringValue contains invalid Unicode") from exc
        return item
    if field == "boolValue":
        if type(item) is not bool:
            raise TraceValidationError("OTLP boolValue must be a boolean")
        return item
    if field == "intValue":
        if type(item) is int:
            number = item
        elif isinstance(item, str) and len(item) <= 20 and re.fullmatch(r"-?(0|[1-9][0-9]*)", item):
            number = int(item)
        else:
            raise TraceValidationError("OTLP intValue must be a signed decimal integer")
        if not -(2**63) <= number < 2**63:
            raise TraceValidationError("OTLP intValue exceeds signed 64-bit range")
        return number
    if field == "doubleValue":
        if isinstance(item, str) and item in {"NaN", "Infinity", "-Infinity"}:
            return float(item)
        if type(item) not in {int, float}:
            raise TraceValidationError("OTLP doubleValue must be numeric")
        try:
            if not math.isfinite(item):
                raise ValueError("non-finite numeric value")
        except (ValueError, OverflowError) as exc:
            raise TraceValidationError("OTLP doubleValue is outside the supported range") from exc
        return item
    if field == "bytesValue":
        if not isinstance(item, str):
            raise TraceValidationError("OTLP bytesValue must be base64 text")
        try:
            return base64.b64decode(item + "=" * (-len(item) % 4), altchars=b"-_", validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TraceValidationError("OTLP bytesValue is invalid base64") from exc
    if not isinstance(item, dict):
        raise TraceValidationError(f"OTLP {field} must be an object")
    values = _objects(item.get("values", []), field)
    if field == "arrayValue":
        return [_otel_value(entry, depth=depth + 1) for entry in values]
    return _key_values(values, depth=depth + 1)


def _objects(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TraceValidationError(f"OTLP {field} must be an array of objects")
    return value


def _key_values(values: list[dict[str, Any]], *, depth: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in values:
        key = item.get("key")
        if not isinstance(key, str) or key in result:
            raise TraceValidationError("OTLP attribute keys are missing or duplicated")
        result[key] = _otel_value(item.get("value", {}), depth=depth)
    return result


def _attributes(record: dict[str, Any]) -> dict[str, Any]:
    return _key_values(_objects(record.get("attributes", []), "attributes"))


def _string_alias(attrs: dict[str, Any], *names: str) -> str | None:
    """Require populated compatibility aliases to agree; never choose by truthiness."""
    values = [attrs[name] for name in names if name in attrs]
    if not values:
        return None
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise TraceValidationError(f"OTLP {'/'.join(names)} must be non-empty strings")
    if any(value != values[0] for value in values[1:]):
        raise TraceValidationError(f"OTLP {'/'.join(names)} contains contradictory aliases")
    return values[0]


def extract_tool_decisions(payloads: list[dict[str, Any]]) -> list[ToolDecision]:
    decisions: list[ToolDecision] = []
    seen: set[ToolDecision] = set()
    if not isinstance(payloads, list) or len(payloads) > _MAX_PAYLOADS:
        raise TraceValidationError("OTLP payload count is invalid")
    for payload in payloads:
        if not isinstance(payload, dict):
            raise TraceValidationError("OTLP payload must be an object")
        for resource in _objects(payload.get("resourceLogs", []), "resourceLogs"):
            for scope in _objects(resource.get("scopeLogs", []), "scopeLogs"):
                for record in _objects(scope.get("logRecords", []), "logRecords"):
                    attrs = _attributes(record)
                    body = _otel_value(record.get("body", {}))
                    event = attrs.get("event.name")
                    event_is_decision = isinstance(event, str) and event in _DECISION_EVENTS
                    body_is_decision = isinstance(body, str) and body in _DECISION_EVENTS
                    if not (event_is_decision or body_is_decision):
                        continue
                    if ("event.name" in attrs and not event_is_decision) or (body is not None and not body_is_decision):
                        raise TraceValidationError("OTLP event name and body disagree about a tool decision")
                    uid = _string_alias(attrs, "tool_use_id")
                    decision = _string_alias(attrs, "decision", "decision_type")
                    if uid is None or decision not in {"accept", "reject", "cancelled"}:
                        raise TraceValidationError("OTLP tool decision has invalid identifier or decision")
                    name = _string_alias(attrs, "tool_name")
                    source = _string_alias(attrs, "source", "decision_source")
                    session = _string_alias(attrs, "session.id")
                    item = ToolDecision(uid, name, decision, source, session)
                    if item not in seen:
                        seen.add(item)
                        decisions.append(item)
                        if len(decisions) > 100_000:
                            raise TraceValidationError("OTLP decision count exceeds the capture limit")
    return decisions


class LocalOtelCollector:
    """Bounded loopback-only OTLP JSON receiver for one explicit live test."""

    def __init__(self) -> None:
        self._payloads: list[dict[str, Any]] = []
        self._errors: list[str] = []
        self._bytes = 0
        self._lock = threading.Lock()
        self._path = f"/{secrets.token_urlsafe(18)}/v1/logs"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(3)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != outer._path:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= _MAX_REQUEST_BYTES:
                        raise ValueError("telemetry request size is invalid")
                    with outer._lock:
                        if outer._bytes + length > _MAX_TOTAL_BYTES or len(outer._payloads) >= _MAX_PAYLOADS:
                            raise ValueError("telemetry capture limit reached")
                        outer._bytes += length
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("telemetry request was truncated")
                    payload = strict_json_loads(raw, max_bytes=_MAX_REQUEST_BYTES)
                    if not isinstance(payload, dict):
                        raise ValueError("telemetry payload must be an object")
                    with outer._lock:
                        if len(outer._payloads) >= _MAX_PAYLOADS:
                            raise ValueError("telemetry payload limit reached")
                        outer._payloads.append(payload)
                except (ValueError, OSError, socket.timeout) as exc:
                    with outer._lock:
                        if len(outer._errors) < 10:
                            outer._errors.append(str(exc))
                    self.send_response(400)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="agentack-otel", daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}{self._path}"

    def __enter__(self) -> "LocalOtelCollector":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def payloads(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._payloads)

    def errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._errors)
