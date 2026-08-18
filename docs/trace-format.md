# Trace format

AgentAck accepts newline-delimited JSON. Trace schema version `2` is intentionally strict. One file represents one complete session and every event must use the same `session_id`.

## Common fields

Every event includes:

```json
{
  "schema_version": 2,
  "type": "session_end",
  "timestamp": "2026-08-18T12:00:00Z",
  "session_id": "session-123"
}
```

Timestamps must be timezone-aware ISO-8601 values. JSONL line order is the observed event order.

## Action object

```json
{
  "tool": "shell",
  "operation": "run",
  "resource": "workspace",
  "parameters": {
    "argv": ["git", "status"]
  }
}
```

`resource` is optional. `parameters` must contain JSON values only. Unknown action fields are rejected.

## Proposed action

```json
{
  "schema_version": 2,
  "type": "action_proposed",
  "timestamp": "2026-08-18T12:00:00Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "action": {
    "tool": "shell",
    "operation": "run",
    "resource": "workspace",
    "parameters": {"argv": ["git", "status"]}
  }
}
```

## Human presentation

`approval_requested` records the exact structured action presented for human approval:

```json
{
  "schema_version": 2,
  "type": "approval_requested",
  "timestamp": "2026-08-18T12:00:01Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "approval_id": "p1",
  "action": {
    "tool": "shell",
    "operation": "run",
    "resource": "workspace",
    "parameters": {"argv": ["git", "status"]}
  }
}
```

AgentAck compares this presented action with the proposal and later execution. A proposal-to-presentation or presentation-to-execution mismatch produces `ACK003`.

## Approval decision

```json
{
  "schema_version": 2,
  "type": "approval_decision",
  "timestamp": "2026-08-18T12:00:02Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "approval_id": "p1",
  "decision": "allow"
}
```

The decision is linked to the previously recorded human presentation using `approval_id` and `action_id`. It does not carry a caller-supplied action hash.

`expires_at` may be supplied as an explicit ISO-8601 timestamp. Otherwise the policy `max_age_seconds` value applies.

## Executed action

```json
{
  "schema_version": 2,
  "type": "action_executed",
  "timestamp": "2026-08-18T12:00:03Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "approval_id": "p1",
  "action": {
    "tool": "shell",
    "operation": "run",
    "resource": "workspace",
    "parameters": {"argv": ["git", "status"]}
  }
}
```

## Blocked action

A blocked action is a terminal outcome for an `action_id`:

```json
{
  "schema_version": 2,
  "type": "action_blocked",
  "timestamp": "2026-08-18T12:00:03Z",
  "session_id": "session-123",
  "action_id": "a1",
  "approval_id": "p1",
  "reason": "human denied"
}
```

Executing the same action after it was recorded as blocked produces `ACK006`.

## Interrupt

```json
{
  "schema_version": 2,
  "type": "interrupt",
  "timestamp": "2026-08-18T12:00:04Z",
  "session_id": "session-123",
  "reason": "human stop"
}
```

With the default policy, execution after an interrupt produces `ACK008`.

## Session end

A complete trace ends with exactly one terminal `session_end` event:

```json
{
  "schema_version": 2,
  "type": "session_end",
  "timestamp": "2026-08-18T12:00:05Z",
  "session_id": "session-123"
}
```

A missing `session_end` produces `INCOMPLETE`. Events after `session_end` produce `ACK006`.

## Strict parsing

The parser rejects:

- duplicate JSON object keys;
- unsupported schema versions;
- unknown event fields;
- unknown action fields;
- mixed session IDs;
- invalid timestamps;
- oversized lines, excessive event counts and excessive parameter nesting.

These are input-validation errors and return CLI exit code `2`.

## Limits

The default reader allows at most 100,000 events, 1 MB per JSONL line and 20 levels of nested action parameters.
