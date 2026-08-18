# Method

AgentAck evaluates event evidence from an AI-agent workflow rather than trusting the agent's own description of what happened.

## Action identity

An action contains four security-relevant fields:

- `tool`
- `operation`
- optional `resource`
- structured `parameters`

The checker serializes those fields as canonical JSON with sorted keys and hashes the bytes with SHA-256. An approval decision can carry that digest as `approved_action_hash`.

At execution time, the checker hashes the executed action independently. A mismatch produces `ACK003`.

This is a deterministic identity mechanism. It is not a digital signature and does not authenticate the trace producer.

## Event order

JSONL line order is treated as the observed event order. Timestamps are used for approval lifetime checks but do not override line order.

This prevents a later event from becoming a preceding approval merely by carrying an earlier timestamp.

## Denial route-around

An optional `intent_id` links alternate action paths that attempt to achieve the same requested outcome. When an intent is denied, execution through a different `action_id` without a later allow decision for that intent produces `ACK007`.

The quality of this rule depends on trustworthy intent correlation. If an integration omits or mislabels `intent_id`, the checker cannot infer semantic equivalence from arbitrary natural language in version `0.1.0`.

## Interrupt semantics

The default policy treats an `interrupt` event as terminal for the recorded session. Any later `action_executed` event produces `ACK008`.

Integrations with resumable workflows should start a new session or configure a future policy mode with explicit resume semantics rather than silently reusing the interrupted session.
