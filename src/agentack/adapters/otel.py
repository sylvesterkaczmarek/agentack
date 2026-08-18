from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_MAX_REQUEST_BYTES = 5_000_000


@dataclass(frozen=True)
class ToolDecision:
    tool_use_id: str
    tool_name: str | None
    decision: str
    source: str | None


def _otel_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value and isinstance(value["arrayValue"], dict):
        return [_otel_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value and isinstance(value["kvlistValue"], dict):
        return {
            item.get("key"): _otel_value(item.get("value"))
            for item in value["kvlistValue"].get("values", [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        }
    return value


def _attributes(record: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in record.get("attributes", []):
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        result[item["key"]] = _otel_value(item.get("value"))
    return result


def _log_records(payload: dict[str, Any]):  # type: ignore[no-untyped-def]
    for resource_logs in payload.get("resourceLogs", []):
        if not isinstance(resource_logs, dict):
            continue
        for scope_logs in resource_logs.get("scopeLogs", []):
            if not isinstance(scope_logs, dict):
                continue
            for record in scope_logs.get("logRecords", []):
                if isinstance(record, dict):
                    yield record


def extract_tool_decisions(payloads: list[dict[str, Any]]) -> list[ToolDecision]:
    decisions: list[ToolDecision] = []
    for payload in payloads:
        for record in _log_records(payload):
            attrs = _attributes(record)
            body = _otel_value(record.get("body"))
            event_name = attrs.get("event.name") or body
            if event_name not in {"tool_decision", "claude_code.tool_decision"}:
                continue
            tool_use_id = attrs.get("tool_use_id")
            decision = attrs.get("decision") or attrs.get("decision_type")
            if not isinstance(tool_use_id, str) or decision not in {"accept", "reject"}:
                continue
            tool_name = attrs.get("tool_name")
            source = attrs.get("source") or attrs.get("decision_source")
            decisions.append(
                ToolDecision(
                    tool_use_id=tool_use_id,
                    tool_name=tool_name if isinstance(tool_name, str) else None,
                    decision=decision,
                    source=source if isinstance(source, str) else None,
                )
            )
    return decisions


class LocalOtelCollector:
    """Minimal loopback-only OTLP/HTTP JSON receiver for one live adapter test."""

    def __init__(self) -> None:
        self._payloads: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > _MAX_REQUEST_BYTES:
                    self.send_response(413)
                    self.end_headers()
                    return
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.send_response(400)
                    self.end_headers()
                    return
                if isinstance(payload, dict):
                    with outer._lock:
                        outer._payloads.append(payload)
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
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1/logs"

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
