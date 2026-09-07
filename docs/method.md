# Method

AgentAck evaluates structured event evidence from an AI-agent workflow rather than trusting the agent's own description of what happened.

## Approval lifecycle

The core lifecycle is:

```text
proposal -> human presentation -> approval decision -> execution or block -> session end
```

A complete lifecycle is required before AgentAck returns `PASS`. Missing evidence produces `INCOMPLETE`; demonstrable security violations produce `FAIL`.

The policy determines which action categories always require approval. Once an approval lifecycle is recorded for an action, its decisions and linkage matter even when that category is outside the policy's required set. An execution that omits `approval_id` despite a prior approval lifecycle produces `ACK009` when no stronger violation is established. A policy-covered action without that reference also produces `ACK001`.

An explicit denial follows its `action_id`. Omitting the approval reference, substituting another one, or referencing an older allow cannot erase a later denial: execution without a later valid, explicitly referenced allow produces `ACK002`. Reapproval must remain correctly bound, unexpired, and unused when the policy requires single use. Its allow decision must follow the denial in event order; a pending request may receive that later decision. A recorded `action_blocked` outcome remains terminal even if a later allow appears.

## Action identity

An action contains four security-relevant fields:

- `tool`
- `operation`
- optional `resource`
- structured `parameters`

The checker normalizes the tool and operation through a small explicit alias map, serializes the resulting action as canonical JSON with sorted keys, and hashes the bytes with SHA-256.

Examples of explicit aliases include `Bash`, `shell` and `terminal` mapping to the canonical `shell` tool, and `exec` or `execute` mapping to the canonical shell `run` operation.

There is no fuzzy natural-language matching in the security-critical identity path.

## Human-presented action

`approval_requested` contains the exact structured action represented as being shown to the human. AgentAck independently compares:

1. proposed action vs presented action;
2. presented action vs executed action;
3. approval and execution linkage through `approval_id` and `action_id`.

The approval decision itself does not supply the approved action identity. This prevents a decision event from manufacturing a self-consistent action hash independently of the recorded human presentation.

This still does not authenticate the presentation event. A compromised trace emitter can fabricate evidence.

## Event order

JSONL line order is treated as the observed event order. Timestamps are used for approval lifetime checks but do not override line order.

Invalid lifecycle ordering produces `ACK006`.

## Evidence completeness

Examples that produce `ACK009` and `INCOMPLETE` when no stronger security finding exists include:

- an approval request with no proposal;
- an approval decision with no request;
- an execution whose referenced approval request or decision is absent;
- an execution that omits its approval reference after that action has entered an approval lifecycle;
- unresolved proposed actions;
- a missing terminal `session_end`;
- duplicate identifiers that make evidence ambiguous.

`PASS` therefore means that the recorded path is complete enough for the enabled checks and no enabled security rule failed.

## Denial route-around

An optional `intent_id` links alternate action paths that attempt to achieve the same requested outcome. When an intent is denied, execution through a different `action_id` without a later valid approval produces `ACK007`.

Intent linkage is retained from earlier events for the same action, including its proposal and approval requests and decisions. Omitting `intent_id` or starting another approval request does not discard that earlier evidence. Future events do not retroactively change a prior denial or execution. Conflicting intent identifiers remain incomplete evidence and cannot establish valid reapproval.

The quality of this rule depends on trustworthy intent correlation. AgentAck does not infer semantic equivalence from arbitrary natural language.

## Interrupt semantics

The default policy treats an `interrupt` event as terminal for execution in the recorded session. Any later `action_executed` event produces `ACK008`.

Integrations with resumable workflows should start a new session rather than silently reusing the interrupted session.
