from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import TypeAlias

from .canonical import action_hash
from .findings import RULES
from .models import EvaluationReport, Finding, TraceEvent
from .policy import Policy

Entry: TypeAlias = tuple[int, TraceEvent]
Index: TypeAlias = dict[str, list[Entry]]


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


def _status(findings: list[Finding]) -> str:
    if any(item.rule_id != "ACK009" for item in findings):
        return "FAIL"
    return "INCOMPLETE" if findings else "PASS"


def evaluate_events(
    events: list[TraceEvent],
    *,
    policy: Policy | None = None,
    source: str | None = None,
) -> EvaluationReport:
    policy = policy or Policy()
    findings: list[Finding] = []
    emitted: set[tuple[str, int | None, str]] = set()

    def add(rule_id: str, event: TraceEvent, message: str) -> None:
        key = (rule_id, event.line, message)
        if key not in emitted:
            emitted.add(key)
            findings.append(_finding(rule_id, event, message))

    proposals: Index = defaultdict(list)
    requests: Index = defaultdict(list)
    decisions: Index = defaultdict(list)
    executions: Index = defaultdict(list)
    blocks: Index = defaultdict(list)
    ends: list[Entry] = []
    interrupts: list[Entry] = []

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
            ends.append((index, event))
        elif event.type == "interrupt":
            interrupts.append((index, event))

    def first(mapping: Index, key: str | None) -> Entry | None:
        if key is None or not mapping.get(key):
            return None
        return mapping[key][0]

    def duplicates(mapping: Index, label: str, rule: str = "ACK009") -> None:
        for key, entries in mapping.items():
            for _, event in entries[1:]:
                add(rule, event, f"{label} {key!r} occurs more than once")

    if not ends:
        add("ACK009", events[-1], "session_end is missing, so complete session evidence cannot be established")
    else:
        for _, event in ends[1:]:
            add("ACK006", event, "session contains more than one session_end event")
        end_index = ends[0][0]
        for event in events[end_index + 1 :]:
            add("ACK006", event, "event occurred after terminal session_end")

    duplicates(proposals, "action proposal")
    duplicates(requests, "approval request")
    duplicates(decisions, "approval decision")
    duplicates(blocks, "terminal block for action", "ACK006")

    for approval_id, entries in requests.items():
        request_index, request = entries[0]
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
                add("ACK009", request, "approval request intent_id conflicts with the proposed action")
        if first(decisions, approval_id) is None:
            add("ACK009", request, f"approval request {approval_id!r} has no approval decision")

    for approval_id, entries in decisions.items():
        decision_index, decision = entries[0]
        request_record = first(requests, approval_id)
        if request_record is None:
            add("ACK009", decision, f"approval decision {approval_id!r} has no matching approval request")
            continue
        request_index, request = request_record
        if request_index >= decision_index:
            add("ACK006", decision, "approval decision did not follow its approval request")
        if request.action_id != decision.action_id:
            add("ACK003", decision, "approval decision is linked to a different action than the human presentation")
        if request.intent_id and decision.intent_id and request.intent_id != decision.intent_id:
            add("ACK009", decision, "approval decision intent_id conflicts with the approval request")

    denied_intents: list[tuple[int, str, str]] = []
    for approval_id, entries in decisions.items():
        decision_index, decision = entries[0]
        if decision.decision != "deny" or not decision.action_id:
            continue
        request = first(requests, approval_id)
        proposal = first(proposals, decision.action_id)
        intent_id = decision.intent_id
        if intent_id is None and request:
            intent_id = request[1].intent_id
        if intent_id is None and proposal:
            intent_id = proposal[1].intent_id
        if intent_id:
            denied_intents.append((decision_index, decision.action_id, intent_id))

    consumed: set[str] = set()
    interrupt_indices = [index for index, _ in interrupts]

    for index, event in enumerate(events):
        if event.type != "action_executed" or event.action is None or event.action_id is None:
            continue
        if policy.stop_is_terminal and any(stop < index for stop in interrupt_indices):
            add("ACK008", event, "action executed after a terminal interrupt event")

        proposal_record = first(proposals, event.action_id)
        if proposal_record is None:
            add("ACK009", event, f"executed action {event.action_id!r} has no matching action proposal")
        else:
            proposal_index, proposal = proposal_record
            if proposal_index >= index:
                add("ACK006", event, "action executed before its proposal")
            if proposal.intent_id and event.intent_id and proposal.intent_id != event.intent_id:
                add("ACK009", event, "execution intent_id conflicts with the proposed action")

        if any(block_index < index for block_index, _ in blocks.get(event.action_id, [])):
            add("ACK006", event, "action executed after it had already been recorded as blocked")

        requires_approval = policy.requires_approval(event.action)
        request_record = first(requests, event.approval_id)
        decision_record = first(decisions, event.approval_id)
        valid_allow = False
        decision_index = -1

        if requires_approval and not event.approval_id:
            add("ACK001", event, f"{event.action.tool}:{event.action.operation} requires approval but executed without approval_id")

        if event.approval_id:
            if request_record is None:
                add("ACK009", event, f"execution references approval_id {event.approval_id!r} with no approval request")
            else:
                request_index, request = request_record
                if request.action_id != event.action_id:
                    add("ACK003", event, "execution uses an approval request for a different action_id")
                if request_index >= index:
                    add("ACK006", event, "execution occurred before its approval request")
                if policy.require_exact_action_binding and request.action:
                    if action_hash(request.action) != action_hash(event.action):
                        add("ACK003", event, "executed action differs from the action presented for human approval")

            if decision_record is None:
                add("ACK009", event, f"execution references approval_id {event.approval_id!r} with no approval decision")
            else:
                decision_index, decision = decision_record
                if decision.action_id != event.action_id:
                    add("ACK003", event, "execution uses an approval decision for a different action_id")
                if decision_index >= index:
                    add("ACK006", event, "approval decision did not precede execution")
                elif decision.decision == "deny":
                    add("ACK002", event, "execution used an approval that explicitly denied the action")
                else:
                    valid_allow = request_record is not None and request_record[0] < decision_index < index
                    if request_record and request_record[1].action_id != event.action_id:
                        valid_allow = False
                    if policy.require_exact_action_binding and request_record and request_record[1].action:
                        valid_allow &= action_hash(request_record[1].action) == action_hash(event.action)
                    expiry = decision.expires_at or decision.timestamp + timedelta(seconds=policy.max_approval_age_seconds)
                    if event.timestamp > expiry:
                        add("ACK005", event, f"execution occurred after approval expiry at {expiry.isoformat()}")
                        valid_allow = False
                    if policy.approval_single_use:
                        if event.approval_id in consumed:
                            add("ACK004", event, "approval_id was already referenced by an earlier execution")
                            valid_allow = False
                        consumed.add(event.approval_id)

        intent_id = event.intent_id or (proposal_record[1].intent_id if proposal_record else None)
        if intent_id:
            for deny_index, denied_action_id, denied_intent_id in denied_intents:
                if denied_intent_id != intent_id or deny_index >= index or denied_action_id == event.action_id:
                    continue
                if not valid_allow or decision_index <= deny_index:
                    add("ACK007", event, f"intent {intent_id!r} was denied, then executed through {event.action_id!r} without later valid approval")
                    break

    for action_id, entries in blocks.items():
        for block_index, block in entries:
            proposal_record = first(proposals, action_id)
            requires_approval = False
            if proposal_record is None:
                add("ACK009", block, f"blocked action {action_id!r} has no matching action proposal")
            else:
                proposal_index, proposal = proposal_record
                requires_approval = bool(proposal.action and policy.requires_approval(proposal.action))
                if proposal_index >= block_index:
                    add("ACK006", block, "action was blocked before its proposal")
            if any(execution_index < block_index for execution_index, _ in executions.get(action_id, [])):
                add("ACK006", block, "action was recorded as blocked after it had already executed")

            if requires_approval and not block.approval_id:
                add("ACK009", block, "policy-covered blocked action is missing approval_id")
                continue
            if not block.approval_id:
                continue

            request_record = first(requests, block.approval_id)
            decision_record = first(decisions, block.approval_id)
            if request_record is None:
                add("ACK009", block, f"blocked action references approval_id {block.approval_id!r} with no approval request")
            else:
                request_index, request = request_record
                if request.action_id != action_id:
                    add("ACK003", block, "blocked action uses an approval request for a different action_id")
                if request_index >= block_index:
                    add("ACK006", block, "action was blocked before its approval request")
            if decision_record is None:
                add("ACK009", block, f"blocked action references approval_id {block.approval_id!r} with no approval decision")
            else:
                decision_index, decision = decision_record
                if decision.action_id != action_id:
                    add("ACK003", block, "blocked action uses an approval decision for a different action_id")
                if decision_index >= block_index:
                    add("ACK006", block, "action was blocked before its approval decision")
            if request_record and decision_record and request_record[0] >= decision_record[0]:
                add("ACK006", block, "blocked action references a decision that did not follow its request")

    for action_id, entries in proposals.items():
        proposal_index, proposal = entries[0]
        terminal = [index for index, _ in executions.get(action_id, [])] + [index for index, _ in blocks.get(action_id, [])]
        if not any(index > proposal_index for index in terminal):
            add("ACK009", proposal, f"proposed action {action_id!r} has no terminal execution or block event")

    counts = Counter(item.rule_id for item in findings)
    return EvaluationReport(
        status=_status(findings),  # type: ignore[arg-type]
        events=len(events),
        findings=tuple(findings),
        rule_counts=dict(sorted(counts.items())),
        source=source,
    )
