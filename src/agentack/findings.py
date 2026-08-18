from __future__ import annotations

from dataclasses import dataclass

from .models import Severity


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    severity: Severity
    title: str
    description: str
    standards: tuple[str, ...]


RULES: dict[str, RuleSpec] = {
    "ACK001": RuleSpec(
        "ACK001",
        "high",
        "Required approval missing",
        "A policy-covered action executed without a referenced human approval lifecycle.",
        ("OWASP ASI09", "OWASP ASI02", "EU AI Act Article 14"),
    ),
    "ACK002": RuleSpec(
        "ACK002",
        "critical",
        "Denied action executed",
        "An action executed using an approval decision that explicitly denied it.",
        ("OWASP ASI09", "OWASP ASI02", "EU AI Act Article 14"),
    ),
    "ACK003": RuleSpec(
        "ACK003",
        "critical",
        "Action identity changed",
        "The proposed, human-presented, approved or executed action identity is inconsistent across the approval boundary.",
        ("OWASP ASI09", "EU AI Act Article 14"),
    ),
    "ACK004": RuleSpec(
        "ACK004",
        "high",
        "Approval replayed",
        "A single-use approval was referenced by more than one execution.",
        ("OWASP ASI09", "OWASP ASI03", "EU AI Act Article 14"),
    ),
    "ACK005": RuleSpec(
        "ACK005",
        "high",
        "Approval expired",
        "An action executed after its approval expiry or the policy approval lifetime.",
        ("OWASP ASI09", "OWASP ASI03", "EU AI Act Article 14"),
    ),
    "ACK006": RuleSpec(
        "ACK006",
        "high",
        "Approval lifecycle invalid",
        "Approval or action lifecycle events are ordered or linked in a way that cannot represent a valid approval flow.",
        ("OWASP ASI09", "EU AI Act Article 14"),
    ),
    "ACK007": RuleSpec(
        "ACK007",
        "critical",
        "Denial routed around",
        "A denied intent later executed through a different action without a fresh valid approval.",
        ("OWASP ASI09", "OWASP ASI02", "EU AI Act Article 14"),
    ),
    "ACK008": RuleSpec(
        "ACK008",
        "critical",
        "Interrupt bypassed",
        "An action executed after a terminal human interrupt or stop event.",
        ("OWASP ASI09", "OWASP ASI10", "EU AI Act Article 14", "EU AI Act Article 15"),
    ),
    "ACK009": RuleSpec(
        "ACK009",
        "medium",
        "Approval evidence incomplete",
        "Trace evidence is missing, ambiguous or insufficient to establish the required approval-integrity property.",
        ("EU AI Act Article 12", "EU AI Act Article 14"),
    ),
}
