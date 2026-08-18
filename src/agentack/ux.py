from __future__ import annotations

from collections.abc import Iterable

from .adapters.base import AdapterStatus, AdapterTestResult


def _line(label: str, status: str, width: int = 28) -> str:
    return f"{label:<{width}} {status}"


def render_adapter_test(result: AdapterTestResult) -> str:
    lines = [f"AgentAck  {result.status}", f"Integration: {result.display_name}", ""]
    for check in result.checks:
        lines.append(_line(check.label, check.status))
    problems = [check for check in result.checks if check.status in {"FAIL", "INCOMPLETE"}]
    if problems:
        lines.append("")
        lines.append("Details")
        for check in problems:
            lines.append(f"- {check.label}: {check.detail}")
    if result.notes:
        lines.append("")
        lines.append("Notes")
        lines.extend(f"- {note}" for note in result.notes)
    return "\n".join(lines)


def render_doctor(statuses: Iterable[AdapterStatus], discovered: Iterable[tuple[str, str, str | None]]) -> str:
    lines = ["AgentAck doctor", ""]
    for status in statuses:
        state = "READY" if status.testable else "NOT FOUND" if not status.installed else "DETECTED"
        extra = status.version or status.executable or ""
        lines.append(f"{status.display_name:<20} {state:<10} {extra}".rstrip())
        if status.detail:
            lines.append(f"  {status.detail}")
    for display_name, state, detail in discovered:
        lines.append(f"{display_name:<20} {state:<10}".rstrip())
        if detail:
            lines.append(f"  {detail}")
    if any(status.testable for status in statuses):
        lines.append("")
        lines.append("Run: agentack test claude")
    else:
        lines.append("")
        lines.append("No live AgentAck adapter is ready on this machine. `agentack demo` still works without an agent account.")
    return "\n".join(lines)
