from __future__ import annotations

from collections import Counter, defaultdict
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


def _report_status(findings: list[Finding]) -> str:
    if any(finding.rule_id != "ACK009" for finding in findings):
        return "FAIL"
    if findings:
        return "INCOMPLETE"
    return "PASS"


def evaluate_events(
    events: list[TraceEvent],
    *,
    policy: Policy | None = None,
    source: str | None = None,
) -> EvaluationReport:
    policy = policy or Policy()
    findings: list[Finding] = []
    seen_findings: set[tuple[str, int | None, str]] = set()

    def add(rule_id: str, event: TraceEvent, message: str) -> None:
        key = (rule_id, event.line, message)
        if key not in seen_findings:
            findings.append(_finding(rule_id, event, message))
            seen_findings.add(key)

    proposals: dict[str, list[tuple[int, TraceEvent]]] = defaultdict(list)
    requests: dict[str, list[tuple[int, TraceEvent]]] = defaultdict(list)
    decisions: dict[str, list[tuple[int, TraceEvent]]] = defaultdict(list)
    executions: dict[str, list[tuple[int, TraceEvent]]] = defaultdict(list)
    blocks: dict[str, list[tuple[int, TraceEvent]]] = defaultdict(list)
    session_ends: list[tuple[int, TraceEvent]] = []
    interrupts: list[tuple[int, TraceEvent]] = []

    for index, event in enumerate(events):
        if event.type == "action_proposed" and event.action_id:
            proposals[event.action_id].append((index, event))
        elif event.type == "approval_requested" and event.approval_id:
            requests[event.approval_id].append((index, event))
        elif event.type == "approval_decision" and event.approval_id:
            decisions[event.approval_id].append((index, event))
        elif event.type == "action_executed" and event.action_id:
            executions[event.action_id].append((index, event))
        elif event.type == "action_blocked" and event.action_id:
            blocks[event.action_id].append((index, event))
        elif event.type == "session_end":
            session_ends.append((index, event))
        elif event.type == "interrupt":
            interrupts.append((index, event))

    last_event = events[-1]
    if not session_ends:
        add("ACK009", last_event, "session_end is missing, so complete session evidence cannot be established")
    else:
        for _, duplicate in session_ends[1:]:
            add("ACK006", duplicate, "session contains more than one session_end event")
        end_index, _ = session_ends[0]
        for later in events[end_index + 1 :]:
            add("ACK006", later, "event occurred after terminal session_end")

    for action_id, items in proposals.items():
        for _, duplicate in items[1:]:
            add("ACK009", duplicate, f"action_id {action_id!r} was proposed more than once")
    for approval_id, items in requests.items():
        for _, duplicate in items[1:]:
            add("ACK009", duplicate, f"approval_id {approval_id!r} was requested more than once")
    for approval_id, items in decisions.items():
        for _, duplicate in items[1:]:
            add("ACK009", duplicate, f"approval_id {approval_id!r} has multiple decisions")

    def first(mapping: dict[str, list[tuple[int, TraceEvent]]], key: str | None) -> tuple[int, TraceEvent] | None:
        if key is None or key not in mapping or not mapping[key]:
            return None
        return mapping[key][0]

    for approval_id, request_items in requests.items():
        request_index, request = request_items[0]
        proposal_record = first(proposals, request.action_id)
        if proposal_record is None:
            add("ACK009", request, f"approval request {approval_id!r} has no matching action proposal")
        else:
            proposal_index, proposal = proposal_record
            if proposal_index >= request_index:
                add("ACK006", request, "approval request did not follow its action proposal")
            if policy.require_exact_action_binding and proposal.action and request.action:
                if action_hash(proposal.action) != action_hash(request.action):
                    add("ACK003", request, "action presented for human approval differs from the proposed action")
            if proposal.intent_id and request.intent_id and proposal.intent_id != request.intent_id:
                add("ACK009", request, "approval request intent_id conflicts with the proposed action intent_id")

        decision_record = first(decisions, approval_id)
        if decision_record is None:
            add("ACK009", request, f"approval request {approval_id!r} has no approval decision")

    for approval_id, decision_items in decisions.items():
        decision_index, decision = decision_items[0]
        request_record = first(requests, approval_id)
        if request_record is None:
            add("ACK009", decision, f"approval decision {approval_id!r} has no matching approval request")
            continue
        request_index, request = request_record
        if request_index >= decision_index:
            add("ACK006", decision, "approval decision did not follow its approval request")
        if request.action_id != decision.action_id:
            add("ACK003", decision, "approval decision is linked to a different action than the human-presented request")
        if request.intent_id and decision.intent_id and request.intent_id != decision.intent_id:
            add("ACK009", decision, "approval decision intent_id conflicts with the approval request intent_id")

    denied_intents: list[tuple[int, str, str]] = []
    for approval_id, decision_items in decisions.items():
        decision_index, decision = decision_items[0]
        if decision.decision != "deny" or not decision.action_id:
            continue
        request_record = first(requests, approval_id)
        proposal_record = first(proposals, decision.action_id)
        intent_id = decision.intent_id
        if intent_id is None and request_record is not None:
            intent_id = request_record[1].intent_id
        if intent_id is None and proposal_record is not None:
            intent_id = proposal_record[1].intent_id
        if intent_id:
            denied_intents.append((decision_index, decision.action_id, intent_id))

    consumed: set[str] = set()
    interrupt_indices = [index for index, _ in interrupts]

    for index, event in enumerate(events):
        if event.type != "action_executed" or event.action is None or event.action_id is None:
            continue

        if policy.stop_is_terminal and any(interrupt_index < index for interrupt_index in interrupt_indices):
            add("ACK008", event, "action executed after a terminal interrupt event")

        proposal_record = first(proposals, event.action_id)
        if proposal_record is None:
            add("ACK009", event, f"executed action {event.action_id!r} has no matching action proposal")
        else:
            proposal_index, proposal = proposal_record
            if proposal_index >= index:
                add("ACK006", event, "action executed before its proposal")
            if proposal.intent_id and event.intent_id and proposal.intent_id != event.intent_id:
                add("ACK009", event, "execution intent_id conflicts with the proposed action intent_id")

        for block_index, _ in blocks.get(event.action_id, []):
            if block_index < index:
                add("ACK006", event, "action executed after it had already been recorded as blocked")
                break

        requires_approval = policy.requires_approval(event.action)
        request_record = first(requests, event.approval_id)
        decision_record = first(decisions, event.approval_id)
        valid_fresh_allow = False
        decision_index = -1

        if requires_approval and not event.approval_id:
            add(
                "ACK001",
                event,
                f"{event.action.tool}:{event.action.operation} requires approval under policy but executed without approval_id",
            )

        if event.approval_id:
            if request_record is None:
                add("ACK009", event, f"execution references approval_id {event.approval_id!r} with no approval request")
            if decision_record is None:
                add("ACK009", event, f"execution references approval_id {event.approval_id!r} with no approval decision")

            if request_record is not None:
                request_index, request = request_record
                if request.action_id != event.action_id:
                    add("ACK003", event, "execution uses an approval request for a different action_id")
                if request_index >= index:
                    add("ACK006", event, "execution occurred before its approval request")
                if policy.require_exact_action_binding and request.action:
                    if action_hash(request.action) != action_hash(event.action):
                        add("ACK003", event, "executed action differs from the action presented for human approval")

            if decision_record is not None:
                decision_index, decision = decision_record
                if decision.action_id != event.action_id:
                    add("ACK003", event, "execution uses an approval decision for a different action_id")
                if decision_index >= index:
                    add("ACK006", event, "approval decision did not precede execution")
                elif decision.decision == "deny":
                    add("ACK002", event, "execution used an approval that explicitly denied the action")
                else:
                    valid_fresh_allow = request_record is not None and request_record[0] < decision_index < index
                    if request_record is not None and request_record[1].action_id != event.action_id:
                        valid_fresh_allow = False
                    if policy.require_exact_action_binding and request_record is not None and request_record[1].action:
                        if action_hash(request_record[1].action) != action_hash(event.action):
                            valid_fresh_allow = False

                    expiry = decision.expires_at or (
                        decision.timestamp + timedelta(seconds=policy.max_approval_age_seconds)
                    )
                    if event.timestamp > expiry:
                        add("ACK005", event, f"execution occurred after approval expiry at {expiry.isoformat()}")
                        valid_fresh_allow = False

                    if policy.approval_single_use:
                        if event.approval_id in consumed:
                            add("ACK004", event, "approval_id was already referenced by an earlier execution")
                            valid_fresh_allow = False
                        consumed.add(event.approval_id)

        intent_id = event.intent_id
        if intent_id is None and proposal_record is not None:
            intent_id = proposal_record[1].intent_id
        if intent_id:
            for deny_index, denied_action_id, denied_intent_id in denied_intents:
                if denied_intent_id != intent_id or deny_index >= index or denied_action_id == event.action_id:
                    continue
                if not valid_fresh_allow or decision_index <= deny_index:
                    add(
                        "ACK007",
                        event,
                        f"intent {intent_id!r} was denied, then executed through action_id {event.action_id!r} without a later valid approval",
                    )
                    break

    for action_id, block_items in blocks.items():
        for block_index, block in block_items:
            proposal_record = first(proposals, action_id)
            if proposal_record is None:
                add("ACK009", block, f"blocked action {action_id!r} has no matching action proposal")
            elif proposal_record[0] >= block_index:
                add("ACK006", block, "action was blocked before its proposal")
            if any(execution_index < block_index for execution_index, _ in executions.get(action_id, [])):
                add("ACK006", block, "action was recorded as blocked after it had already executed")
            if block.approval_id:
                request_record = first(requests, block.approval_id)
                decision_record = first(decisions, block.approval_id)
                if request_record is None:
                    add("ACK009", block, f"blocked action references approval_id {block.approval_id!r} with no approval request")
                if decision_record is None:
                    add("ACK009", block, f"blocked action references approval_id {block.approval_id!r} with no approval decision")
                if request_record is not None and request_record[1].action_id != action_id:
                    add("ACK003", block, "blocked action uses an approval request for a different action_id")
                if decision_record is not None and decision_record[1].action_id != action_id:
                    add("ACK003", block, "blocked action uses an approval decision for a different action_id")

    for action_id, proposal_items in proposals.items():
        proposal_index, proposal = proposal_items[0]
        terminal_indices = [index for index, _ in executions.get(action_id, [])] + [index for index, _ in blocks.get(action_id, [])]
        if not any(index > proposal_index for index in terminal_indices):
            add("ACK009", proposal, f"proposed action {action_id!r} has no terminal execution or block event")

    counts = Counter(finding.rule_id for finding in findings)
    return EvaluationReport(
        status=_report_status(findings),  # type: ignore[arg-type]
        events=len(events),
        findings=tuple(findings),
        rule_counts=dict(sorted(counts.items())),
        source=source,
    )
