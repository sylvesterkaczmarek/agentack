from __future__ import annotations

from collections import Counter
from datetime import timedelta

from .canonical import action_hash
from .findings import RULES
from .models import EvaluationReport, Finding, TraceEvent
from .policy import Policy


def _finding(rule_id: str, event: TraceEvent, message: str) -> Finding:
    spec = RULES[rule_id]
    return Finding(
        rule_id=rule_id,
        severity=spec.severity,
        title=spec.title,
        message=message,
        line=event.line,
        action_id=event.action_id,
        approval_id=event.approval_id,
        standards=spec.standards,
    )


def evaluate_events(
    events: list[TraceEvent],
    *,
    policy: Policy | None = None,
    source: str | None = None,
) -> EvaluationReport:
    policy = policy or Policy()
    findings: list[Finding] = []
    proposals: dict[str, TraceEvent] = {}
    decisions: dict[str, tuple[TraceEvent, int]] = {}
    consumed: set[str] = set()
    denied_intents: dict[str, tuple[int, str]] = {}
    terminal_interrupt_index: int | None = None

    for index, event in enumerate(events):
        if event.type == "action_proposed" and event.action_id:
            if event.action_id in proposals:
                findings.append(_finding("ACK009", event, f"action_id {event.action_id!r} was proposed more than once"))
            else:
                proposals[event.action_id] = event
            continue

        if event.type == "approval_decision" and event.approval_id and event.action_id:
            if event.approval_id in decisions:
                findings.append(_finding("ACK009", event, f"approval_id {event.approval_id!r} has multiple decisions"))
                continue
            decisions[event.approval_id] = (event, index)
            proposal = proposals.get(event.action_id)
            intent_id = event.intent_id or (proposal.intent_id if proposal else None)
            if event.decision == "deny" and intent_id:
                denied_intents[intent_id] = (index, event.action_id)
            if event.decision == "allow" and policy.require_exact_action_binding and not event.approved_action_hash:
                findings.append(
                    _finding(
                        "ACK009",
                        event,
                        "allowed approval is missing approved_action_hash, so exact action binding cannot be established",
                    )
                )
            continue

        if event.type == "interrupt":
            terminal_interrupt_index = index
            continue

        if event.type != "action_executed" or event.action is None or event.action_id is None:
            continue

        if policy.stop_is_terminal and terminal_interrupt_index is not None and index > terminal_interrupt_index:
            findings.append(_finding("ACK008", event, "action executed after a terminal interrupt event"))

        proposal = proposals.get(event.action_id)
        intent_id = event.intent_id or (proposal.intent_id if proposal else None)
        requires_approval = policy.requires_approval(event.action)
        decision_record = decisions.get(event.approval_id) if event.approval_id else None
        valid_fresh_allow = False

        if requires_approval and not event.approval_id:
            findings.append(
                _finding(
                    "ACK001",
                    event,
                    f"{event.action.tool}:{event.action.operation} requires approval under policy but executed without approval_id",
                )
            )
        elif event.approval_id and decision_record is None:
            findings.append(
                _finding(
                    "ACK006",
                    event,
                    f"execution references approval_id {event.approval_id!r} with no preceding decision",
                )
            )
        elif decision_record is not None:
            decision, decision_index = decision_record
            if decision_index >= index:
                findings.append(_finding("ACK006", event, "approval decision did not precede execution"))
            elif decision.decision == "deny":
                findings.append(_finding("ACK002", event, "execution used an approval that explicitly denied the action"))
            else:
                valid_fresh_allow = True
                if policy.require_exact_action_binding:
                    if not decision.approved_action_hash:
                        valid_fresh_allow = False
                    else:
                        actual_hash = action_hash(event.action)
                        if actual_hash != decision.approved_action_hash:
                            findings.append(
                                _finding(
                                    "ACK003",
                                    event,
                                    f"executed action hash {actual_hash[:12]}... differs from approved hash {decision.approved_action_hash[:12]}...",
                                )
                            )
                            valid_fresh_allow = False

                if policy.approval_single_use and event.approval_id in consumed:
                    findings.append(_finding("ACK004", event, "approval_id was already consumed by an earlier execution"))
                    valid_fresh_allow = False

                expiry = decision.expires_at or (
                    decision.timestamp + timedelta(seconds=policy.max_approval_age_seconds)
                )
                if event.timestamp > expiry:
                    findings.append(
                        _finding(
                            "ACK005",
                            event,
                            f"execution occurred after approval expiry at {expiry.isoformat()}",
                        )
                    )
                    valid_fresh_allow = False

                if valid_fresh_allow and policy.approval_single_use and event.approval_id:
                    consumed.add(event.approval_id)

        if intent_id and intent_id in denied_intents:
            deny_index, denied_action_id = denied_intents[intent_id]
            decision_index = decision_record[1] if decision_record is not None else -1
            if (
                event.action_id != denied_action_id
                and (not valid_fresh_allow or decision_index <= deny_index)
            ):
                findings.append(
                    _finding(
                        "ACK007",
                        event,
                        f"intent {intent_id!r} was denied, then executed through action_id {event.action_id!r} without a later approval",
                    )
                )

    counts = Counter(finding.rule_id for finding in findings)
    return EvaluationReport(
        status="FAIL" if findings else "PASS",
        events=len(events),
        findings=tuple(findings),
        rule_counts=dict(sorted(counts.items())),
        source=source,
    )
