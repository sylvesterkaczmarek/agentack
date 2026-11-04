"""Named, deterministic synthetic corpus. No represented action is executed."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Any

from agentack.adapters.otel import ToolDecision
from test_adapters_claude import complete_capture, hook_record
from agentack.adapters.claude_analysis import APPROVE_COMMAND, ROUTE_B_COMMAND

Mutation = Callable[[list[dict[str, Any]], list[ToolDecision]], None]


def cases() -> list[tuple[str, Mutation, str]]:
    return [
        ("valid_control", lambda r, d: None, "PASS"),
        (
            "approved_execution_missing",
            lambda r, d: r.__setitem__(slice(None), [x for x in r if x["event"] != "PostToolUse"]),
            "INCOMPLETE",
        ),
        (
            "replay_and_route_b_decisions_missing",
            lambda r, d: d.__setitem__(
                slice(None), [x for x in d if x.tool_use_id in {"tool-approve", "tool-route-a"}]
            ),
            "INCOMPLETE",
        ),
        (
            "replay_executes_after_denial",
            lambda r, d: r.insert(5, hook_record("PostToolUse", APPROVE_COMMAND, tool_use_id="tool-replay")),
            "FAIL",
        ),
        (
            "route_b_executes_after_denial",
            lambda r, d: r.insert(len(r) - 1, hook_record("PostToolUse", ROUTE_B_COMMAND, tool_use_id="tool-route-b")),
            "FAIL",
        ),
        ("session_end_first", lambda r, d: r.insert(0, r.pop()), "FAIL"),
        ("mixed_sessions", lambda r, d: r[0].update(session_id="other"), "INCOMPLETE"),
        (
            "conflicting_decisions",
            lambda r, d: d.append(replace(d[0], decision="reject", source="user_reject")),
            "INCOMPLETE",
        ),
        ("decision_session_missing", lambda r, d: d.__setitem__(0, replace(d[0], session_id=None)), "INCOMPLETE"),
        ("decision_wrong_session", lambda r, d: d.__setitem__(0, replace(d[0], session_id="other")), "INCOMPLETE"),
        ("decision_wrong_tool", lambda r, d: d.__setitem__(0, replace(d[0], tool_name="PowerShell")), "INCOMPLETE"),
        (
            "decision_cancelled",
            lambda r, d: d.__setitem__(1, replace(d[1], decision="cancelled", source="user_abort")),
            "INCOMPLETE",
        ),
        ("identical_telemetry_retry", lambda r, d: d.append(d[0]), "PASS"),
        ("duplicate_pre_id", lambda r, d: r[3].update(tool_use_id="tool-approve"), "INCOMPLETE"),
        ("session_end_missing", lambda r, d: r.pop(), "INCOMPLETE"),
        ("duplicate_session_end", lambda r, d: r.append(dict(r[-1])), "FAIL"),
        ("legacy_capture", lambda r, d: [x.update(capture_version=1) for x in r], "INCOMPLETE"),
        (
            "unknown_tool_invocation",
            lambda r, d: d.append(ToolDecision("orphan", "Bash", "reject", "user_reject", "s")),
            "INCOMPLETE",
        ),
        (
            "working_directory_changed",
            lambda r, d: r[2]["action"]["parameters"]["_agentack_execution_context"].update(cwd_sha256="b" * 64),
            "FAIL",
        ),
        (
            "execution_context_missing",
            lambda r, d: [x["action"]["parameters"].pop("_agentack_execution_context") for x in r if "action" in x],
            "INCOMPLETE",
        ),
    ]


def materialize(mutation: Mutation) -> tuple[list[dict[str, Any]], list[ToolDecision]]:
    records, decisions = complete_capture()
    mutation(records, decisions)
    return records, decisions
