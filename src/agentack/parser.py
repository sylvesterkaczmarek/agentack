from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import TraceEvent, TraceValidationError

MAX_LINE_BYTES = 1_000_000
MAX_EVENTS = 100_000


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TraceValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def read_jsonl_with_digest(
    path: str | Path,
    *,
    max_events: int = MAX_EVENTS,
) -> tuple[list[TraceEvent], str]:
    source = Path(path)
    events: list[TraceEvent] = []
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            digest.update(raw)
            if len(raw) > MAX_LINE_BYTES:
                raise TraceValidationError(f"line {line_number} exceeds {MAX_LINE_BYTES} bytes")
            if not raw.strip():
                continue
            if len(events) >= max_events:
                raise TraceValidationError(f"trace exceeds maximum event count {max_events}")
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TraceValidationError(f"line {line_number} is not UTF-8") from exc
            try:
                data = json.loads(decoded, object_pairs_hook=_strict_object)
            except TraceValidationError as exc:
                raise TraceValidationError(f"line {line_number}: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise TraceValidationError(f"line {line_number} is not valid JSON: {exc.msg}") from exc
            try:
                events.append(TraceEvent.from_dict(data, line=line_number))
            except TraceValidationError as exc:
                raise TraceValidationError(f"line {line_number}: {exc}") from exc
    if not events:
        raise TraceValidationError("trace contains no events")
    session_ids = {event.session_id for event in events}
    if len(session_ids) != 1:
        raise TraceValidationError("one trace file must contain exactly one session_id")
    return events, digest.hexdigest()


def read_jsonl(path: str | Path, *, max_events: int = MAX_EVENTS) -> list[TraceEvent]:
    events, _ = read_jsonl_with_digest(path, max_events=max_events)
    return events


def write_jsonl(path: str | Path, events: list[TraceEvent]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")
