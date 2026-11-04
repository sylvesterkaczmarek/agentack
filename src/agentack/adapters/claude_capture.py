from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..canonical import action_hash
from ..models import Action
from ..validation import MAX_EVENTS, MAX_LINE_BYTES, MAX_TRACE_BYTES, strict_json_loads

_CAPTURE_VERSION = 2
_MAX_HOOK_INPUT_BYTES = 1_000_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def claude_action(tool_name: str, tool_input: dict[str, Any], *, cwd: str | None = None) -> Action:
    """Convert a Claude Code tool event into AgentAck's framework-neutral action model."""
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("Claude hook tool_name must be a non-empty string")
    if not isinstance(tool_input, dict):
        raise ValueError("Claude hook tool_input must be an object")

    name = tool_name.strip()
    lowered = name.lower()
    parameters = dict(tool_input)
    if "_agentack_execution_context" in parameters:
        raise ValueError("reserved AgentAck context key in tool input")
    context = {"native_tool": name}
    if cwd is not None:
        if not isinstance(cwd, str) or not cwd:
            raise ValueError("hook cwd must be a non-empty string")
        context["cwd_sha256"] = hashlib.sha256(cwd.encode("utf-8")).hexdigest()
    parameters["_agentack_execution_context"] = context

    if name == "Bash":
        return Action("shell", "run", resource="workspace", parameters=parameters)
    if name in {"Write", "Edit", "NotebookEdit"}:
        resource = tool_input.get("file_path") or tool_input.get("notebook_path")
        return Action("filesystem", "write", resource=str(resource) if resource else None, parameters=parameters)
    if name in {"Read", "Glob", "Grep"}:
        resource = tool_input.get("file_path") or tool_input.get("path")
        return Action("filesystem", "read", resource=str(resource) if resource else None, parameters=parameters)
    if name == "WebFetch":
        resource = tool_input.get("url")
        return Action("network", "request", resource=str(resource) if resource else None, parameters=parameters)
    if name == "WebSearch":
        return Action("network", "search", parameters=parameters)
    if lowered.startswith("mcp__"):
        pieces = name.split("__", 2)
        resource = "/".join(pieces[1:]) if len(pieces) == 3 else name
        return Action("mcp", "call", resource=resource, parameters=parameters)
    return Action(name, "call", parameters=parameters)


def _capture_record(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "capture_version": _CAPTURE_VERSION,
        "event": event_name,
        "observed_at": _now_iso(),
        "session_id": payload.get("session_id"),
    }
    if event_name in {"PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure"}:
        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
            raise ValueError(f"{event_name} hook input is missing tool_name/tool_input")
        action = claude_action(tool_name, tool_input, cwd=payload.get("cwd"))
        record.update(
            {
                "tool_name": tool_name,
                "tool_use_id": payload.get("tool_use_id"),
                "action": action.to_dict(),
                "action_hash": action_hash(action),
            }
        )
    if event_name == "SessionEnd":
        record["reason"] = payload.get("reason")
    return record


def record_hook_event(event_name: str, capture_path: str | Path, raw_input: bytes) -> None:
    """Record sanitized Claude hook metadata without changing Claude's permission decision."""
    if len(raw_input) > _MAX_HOOK_INPUT_BYTES:
        raise ValueError("Claude hook input exceeds AgentAck size limit")
    try:
        payload = strict_json_loads(raw_input)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Claude hook input is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Claude hook input must be a JSON object")
    if payload.get("hook_event_name", event_name) != event_name:
        raise ValueError("hook event name does not match invocation")
    record = _capture_record(event_name, payload)
    from .claude_validation import validate_capture_records
    validate_capture_records([record])
    target = Path(capture_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")


def read_capture(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    total = 0
    with target.open("rb") as handle:
        while line := handle.readline(MAX_LINE_BYTES + 1):
            total += len(line)
            if len(line) > MAX_LINE_BYTES or total > MAX_TRACE_BYTES or len(records) >= MAX_EVENTS:
                raise ValueError("capture exceeds AgentAck size limit")
            if line.strip():
                record = strict_json_loads(line)
                if not isinstance(record, dict):
                    raise ValueError("capture record must be an object")
                records.append(record)
    from .claude_validation import validate_capture_records
    validate_capture_records(records)
    return records
