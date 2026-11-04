from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import TraceEvent, TraceValidationError
from .validation import MAX_EVENTS, MAX_LINE_BYTES, MAX_TRACE_BYTES, strict_json_loads, validate_events


def read_jsonl_with_digest(
    path: str | Path,
    *,
    max_events: int = MAX_EVENTS,
) -> tuple[list[TraceEvent], str]:
    if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
        raise TraceValidationError(f"max_events must be from 1 to {MAX_EVENTS}")
    events: list[TraceEvent] = []
    digest = hashlib.sha256()
    total_bytes = 0
    with Path(path).open("rb") as handle:
        line_number = 0
        while raw := handle.readline(MAX_LINE_BYTES + 1):
            line_number += 1
            total_bytes += len(raw)
            if len(raw) > MAX_LINE_BYTES:
                raise TraceValidationError(f"line {line_number} exceeds {MAX_LINE_BYTES} bytes")
            if total_bytes > MAX_TRACE_BYTES:
                raise TraceValidationError(f"trace exceeds {MAX_TRACE_BYTES} bytes")
            digest.update(raw)
            if not raw.strip():
                continue
            if len(events) >= max_events:
                raise TraceValidationError(f"trace exceeds maximum event count {max_events}")
            try:
                data = strict_json_loads(raw)
                events.append(TraceEvent.from_dict(data, line=line_number))
            except TraceValidationError as exc:
                raise TraceValidationError(f"line {line_number}: {exc}") from exc
    return validate_events(events, max_events=max_events), digest.hexdigest()


def read_jsonl(path: str | Path, *, max_events: int = MAX_EVENTS) -> list[TraceEvent]:
    events, _ = read_jsonl_with_digest(path, max_events=max_events)
    return events


def write_jsonl(path: str | Path, events: list[TraceEvent]) -> None:
    normalized = validate_events(events)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for event in normalized:
            handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
            handle.write("\n")
