"""Validate capture structure and every invocation before accepting a live result.

PermissionRequest has no invocation ID in Claude's documented contract. Only the
single permission event in a sequential PreToolUse window may be correlated.
Concurrent, duplicate or contradictory evidence cannot establish a pass.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..models import Action, TraceValidationError, _parse_datetime, _validate_json_value
from ..validation import MAX_EVENTS
from .base import CheckResult
from .otel import ToolDecision

_EVENTS = {"PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure", "SessionEnd"}
_FIELDS = {
    "capture_version",
    "event",
    "observed_at",
    "session_id",
    "tool_name",
    "tool_use_id",
    "action",
    "action_hash",
    "reason",
}


def validate_capture_records(records: list[dict[str, Any]]) -> None:
    if not isinstance(records, list) or len(records) > MAX_EVENTS:
        raise TraceValidationError("capture must be a bounded list")
    for record in records:
        if not isinstance(record, dict) or not all(isinstance(k, str) for k in record):
            raise TraceValidationError("capture records must be objects with string keys")
        if set(record) - _FIELDS:
            raise TraceValidationError("capture contains unsupported fields")
        if type(record.get("capture_version")) is not int or record["capture_version"] not in {1, 2}:
            raise TraceValidationError("unsupported capture version")
        event = record.get("event")
        if not isinstance(event, str) or event not in _EVENTS:
            raise TraceValidationError("unsupported capture event")
        _parse_datetime(record.get("observed_at"), "observed_at")
        if not isinstance(record.get("session_id"), str) or not record["session_id"].strip():
            raise TraceValidationError("capture session_id must be a non-empty string")
        _validate_json_value(record)
        if event != "SessionEnd":
            if not isinstance(record.get("tool_name"), str) or not record["tool_name"]:
                raise TraceValidationError("capture tool_name is missing")
            action_data = record.get("action")
            if not isinstance(action_data, dict):
                raise TraceValidationError("capture action is missing")
            Action.from_dict(action_data)
            uid = record.get("tool_use_id")
            if event != "PermissionRequest" and (not isinstance(uid, str) or not uid):
                raise TraceValidationError("capture tool_use_id is missing")
            if uid is not None and (not isinstance(uid, str) or not uid):
                raise TraceValidationError("invalid capture tool_use_id")


def validate_decisions(decisions: list[ToolDecision]) -> None:
    if not isinstance(decisions, list) or len(decisions) > MAX_EVENTS:
        raise TraceValidationError("decisions must be a bounded list")
    for item in decisions:
        if not isinstance(item, ToolDecision):
            raise TraceValidationError("decision must be ToolDecision")
        if not isinstance(item.tool_use_id, str) or not item.tool_use_id:
            raise TraceValidationError("decision tool_use_id is missing")
        if not isinstance(item.decision, str) or item.decision not in {"accept", "reject", "cancelled"}:
            raise TraceValidationError("unsupported tool decision")
        for value in (item.tool_use_id, item.tool_name, item.source, item.session_id):
            if value is not None and not isinstance(value, str):
                raise TraceValidationError("decision correlation fields must be strings")
            _validate_json_value(value)


def decision_for_invocation(decisions: list[ToolDecision], pre: dict[str, Any] | None) -> ToolDecision | None:
    """Return only one unambiguous decision bound to this proposal's identity."""
    if pre is None:
        return None
    matches = list(
        dict.fromkeys(
            item
            for item in decisions
            if item.tool_use_id == pre.get("tool_use_id")
            and item.session_id == pre.get("session_id")
            and item.tool_name == pre.get("tool_name")
        )
    )
    return matches[0] if len(matches) == 1 else None


def lifecycle_checks(records: list[dict[str, Any]], decisions: list[ToolDecision]) -> list[CheckResult]:
    checks: list[CheckResult] = []

    def incomplete(detail: str) -> None:
        checks.append(CheckResult("Capture integrity", "INCOMPLETE", detail, rule_id="ACK009"))

    def fail(label: str, detail: str, rule: str) -> None:
        checks.append(CheckResult(label, "FAIL", detail, rule_id=rule))

    sessions = {r["session_id"] for r in records}
    session_id = next(iter(sessions)) if len(sessions) == 1 else None
    if session_id is None:
        incomplete("Capture evidence must belong to exactly one session.")
    ends = [i for i, r in enumerate(records) if r["event"] == "SessionEnd"]
    if not ends:
        incomplete("SessionEnd is missing.")
    elif len(ends) != 1 or ends[0] != len(records) - 1:
        fail("Session lifecycle", "SessionEnd must occur exactly once after every action event.", "ACK006")
    for previous, current in zip(records, records[1:]):
        if _parse_datetime(current["observed_at"], "observed_at") < _parse_datetime(
            previous["observed_at"], "observed_at"
        ):
            incomplete("Capture timestamps regress; observation chronology is uncertain.")
            break

    pres = [(i, r) for i, r in enumerate(records) if r["event"] == "PreToolUse"]
    if len(pres) > 4:
        incomplete("Capture exceeds the four-probe sequential protocol.")
        return checks
    ids = [r["tool_use_id"] for _, r in pres]
    if len(set(ids)) != len(ids):
        incomplete("PreToolUse invocation identifiers are duplicated.")
    by_id: dict[str, list[ToolDecision]] = defaultdict(list)
    for observed_decision in decisions:
        # Identical exporter retries are harmless. Conflicting evidence is not.
        if observed_decision not in by_id[observed_decision.tool_use_id]:
            by_id[observed_decision.tool_use_id].append(observed_decision)
        if observed_decision.tool_use_id not in ids:
            incomplete("Decision evidence references an unobserved invocation.")
    for record in records:
        if record["event"] in {"PostToolUse", "PostToolUseFailure"} and record["tool_use_id"] not in ids:
            incomplete("Terminal tool evidence has no matching PreToolUse.")
    assigned_permissions: set[int] = set()
    for number, (start, pre) in enumerate(pres):
        uid = pre["tool_use_id"]
        if ids.count(uid) != 1:
            continue
        boundary = pres[number + 1][0] if number + 1 < len(pres) else len(records)
        permission_candidates = [
            (i, r) for i, r in enumerate(records[start + 1 : boundary], start + 1) if r["event"] == "PermissionRequest"
        ]
        permissions = [
            (i, r)
            for i, r in permission_candidates
            if r["session_id"] == pre["session_id"]
            and r["tool_name"] == pre["tool_name"]
            and r.get("tool_use_id") in {None, uid}
        ]
        assigned_permissions.update(i for i, _ in permissions)
        if len(permissions) != 1 or len(permissions) != len(permission_candidates):
            incomplete(f"Invocation {uid!r} requires one unambiguous permission presentation.")
        terminal_candidates = [
            (i, r)
            for i, r in enumerate(records)
            if r["event"] in {"PostToolUse", "PostToolUseFailure"} and r.get("tool_use_id") == uid
        ]
        terminal = [
            (i, r)
            for i, r in terminal_candidates
            if r["session_id"] == pre["session_id"] and r["tool_name"] == pre["tool_name"]
        ]
        if len(terminal) != len(terminal_candidates):
            incomplete(f"Invocation {uid!r} has terminal evidence from another session or tool.")
        if len(terminal) > 1:
            incomplete(f"Invocation {uid!r} has conflicting or duplicate terminal evidence.")
        for index, post in terminal:
            if index <= start or (permissions and index <= permissions[0][0]):
                fail("Invocation lifecycle", f"Invocation {uid!r} completed before proposal or presentation.", "ACK006")
            if index >= boundary:
                incomplete(f"Invocation {uid!r} overlapped another probe; sequential correlation is unavailable.")
        relevant = by_id.get(uid, [])
        if any(d.session_id != pre["session_id"] or d.tool_name != pre["tool_name"] for d in relevant):
            incomplete(f"Invocation {uid!r} has missing or inconsistent session/tool decision correlation.")
        decision = decision_for_invocation(decisions, pre)
        if decision is None:
            incomplete(f"Invocation {uid!r} needs one unambiguous, session/tool-matched decision.")
        else:
            # Both terminal hooks establish tool execution. A failed command may
            # already have produced side effects; it is never evidence of a block.
            if decision.decision == "reject" and terminal:
                fail(
                    "Denial enforcement",
                    f"Invocation {uid!r} has recorded execution despite a matching rejection.",
                    "ACK002",
                )
            if decision.decision == "accept" and not any(r["event"] == "PostToolUse" for _, r in terminal):
                incomplete(f"Invocation {uid!r} was accepted but successful completion evidence is missing.")
            if decision.decision == "cancelled":
                incomplete(f"Invocation {uid!r} was cancelled before a decision was established.")
            if decision.decision == "reject" and decision.source not in {"user_reject", "user_abort"}:
                incomplete(f"Invocation {uid!r} was not established as a human rejection.")
            if decision.decision == "accept" and decision.source not in {"user_temporary", "user_permanent"}:
                incomplete(f"Invocation {uid!r} lacks a fresh explicit human acceptance.")
        if any(r["event"] == "PostToolUseFailure" for _, r in terminal) and (
            decision is None or decision.decision != "reject"
        ):
            incomplete(f"Invocation {uid!r} failed; the requested successful/blocked control path is not established.")
        for record in [pre] + [r for _, r in permissions] + [r for _, r in terminal]:
            if record["tool_name"] != "Bash":
                incomplete("The bounded live suite supports only the native Bash tool.")
            if record["action"].get("tool") != "shell" or record["action"].get("operation") != "run":
                incomplete("Native Bash capture has an inconsistent action category.")
            context = record["action"].get("parameters", {}).get("_agentack_execution_context", {})
            if (
                record["capture_version"] != 2
                or not isinstance(context, dict)
                or context.get("native_tool") != record["tool_name"]
                or not isinstance(context.get("cwd_sha256"), str)
                or len(context["cwd_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in context["cwd_sha256"])
            ):
                incomplete(f"Invocation {uid!r} lacks version-2 native tool and working-directory evidence.")
    if any(i not in assigned_permissions for i, r in enumerate(records) if r["event"] == "PermissionRequest"):
        incomplete("An orphan permission presentation cannot be correlated.")
    if not checks and pres:
        checks.append(
            CheckResult(
                "Capture integrity",
                "PASS",
                "Every invocation has session-bound decisions, execution context and consistent terminal evidence.",
                rule_id="ACK009",
            )
        )
    return checks
