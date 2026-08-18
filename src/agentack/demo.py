from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Action, TraceEvent

SCENARIOS = (
    "secure",
    "action-swap",
    "denial-bypass",
    "replay",
    "route-around",
    "interrupt-bypass",
    "expired",
    "unapproved",
)

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
SESSION = "demo-session"


def _event(event_type: str, offset: int, **kwargs) -> TraceEvent:  # type: ignore[no-untyped-def]
    return TraceEvent(type=event_type, timestamp=BASE + timedelta(seconds=offset), session_id=SESSION, **kwargs)  # type: ignore[arg-type]


def demo_events(scenario: str) -> list[TraceEvent]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown demo scenario {scenario!r}")

    approved = Action("shell", "run", resource="workspace", parameters={"argv": ["git", "status"]})
    changed = Action("shell", "run", resource="workspace", parameters={"argv": ["curl", "https://example.invalid"]})
    delete = Action("filesystem", "delete", resource="synthetic/report.txt", parameters={})
    alternate = Action("mcp", "call", resource="synthetic-files", parameters={"method": "delete", "path": "report.txt"})
    read = Action("filesystem", "read", resource="synthetic/report.txt", parameters={})

    if scenario == "secure":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=approved),
            _event("approval_requested", 1, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("approval_decision", 2, action_id="a1", intent_id="i1", approval_id="p1", decision="allow"),
            _event("action_executed", 3, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("session_end", 4),
        ]
    if scenario == "action-swap":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=approved),
            _event("approval_requested", 1, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("approval_decision", 2, action_id="a1", intent_id="i1", approval_id="p1", decision="allow"),
            _event("action_executed", 3, action_id="a1", intent_id="i1", approval_id="p1", action=changed),
            _event("session_end", 4),
        ]
    if scenario == "denial-bypass":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=delete),
            _event("approval_requested", 1, action_id="a1", intent_id="i1", approval_id="p1", action=delete),
            _event("approval_decision", 2, action_id="a1", intent_id="i1", approval_id="p1", decision="deny"),
            _event("action_executed", 3, action_id="a1", intent_id="i1", approval_id="p1", action=delete),
            _event("session_end", 4),
        ]
    if scenario == "replay":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=approved),
            _event("approval_requested", 1, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("approval_decision", 2, action_id="a1", intent_id="i1", approval_id="p1", decision="allow"),
            _event("action_executed", 3, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("action_executed", 4, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("session_end", 5),
        ]
    if scenario == "route-around":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="delete-report", action=delete),
            _event("approval_requested", 1, action_id="a1", intent_id="delete-report", approval_id="p1", action=delete),
            _event("approval_decision", 2, action_id="a1", intent_id="delete-report", approval_id="p1", decision="deny"),
            _event("action_blocked", 3, action_id="a1", intent_id="delete-report", approval_id="p1", reason="human denied"),
            _event("action_proposed", 4, action_id="a2", intent_id="delete-report", action=alternate),
            _event("action_executed", 5, action_id="a2", intent_id="delete-report", action=alternate),
            _event("session_end", 6),
        ]
    if scenario == "interrupt-bypass":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=read),
            _event("interrupt", 1, reason="human stop"),
            _event("action_executed", 2, action_id="a1", intent_id="i1", action=read),
            _event("session_end", 3),
        ]
    if scenario == "expired":
        return [
            _event("action_proposed", 0, action_id="a1", intent_id="i1", action=approved),
            _event("approval_requested", 1, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event(
                "approval_decision",
                2,
                action_id="a1",
                intent_id="i1",
                approval_id="p1",
                decision="allow",
                expires_at=BASE + timedelta(seconds=10),
            ),
            _event("action_executed", 20, action_id="a1", intent_id="i1", approval_id="p1", action=approved),
            _event("session_end", 21),
        ]
    return [
        _event("action_proposed", 0, action_id="a1", intent_id="i1", action=approved),
        _event("action_executed", 1, action_id="a1", intent_id="i1", action=approved),
        _event("session_end", 2),
    ]
