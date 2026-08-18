# Trace format

AgentAck accepts newline-delimited JSON. One file represents one session and every event must use the same `session_id`.

## Common fields

```json
{
  "type": "action_proposed",
  "timestamp": "2026-08-18T12:00:00Z",
  "session_id": "session-123"
}
```

Timestamps must be timezone-aware ISO-8601 values.

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

`resource` is optional. `parameters` must contain JSON values only.

## Proposed action

```json
{
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

## Approval request

```json
{
  "type": "approval_requested",
  "timestamp": "2026-08-18T12:00:01Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "approval_id": "p1"
}
```

## Approval decision

An allow decision should include the canonical SHA-256 identity of the action the human approved:

```json
{
  "type": "approval_decision",
  "timestamp": "2026-08-18T12:00:02Z",
  "session_id": "session-123",
  "action_id": "a1",
  "intent_id": "inspect-repo",
  "approval_id": "p1",
  "decision": "allow",
  "approved_action_hash": "64-character-sha256-hex-value"
}
```

A deny decision does not require `approved_action_hash`.

`expires_at` may be supplied as an explicit ISO-8601 timestamp. Otherwise the policy `max_age_seconds` value applies.

## Executed action

```json
{
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

## Interrupt

```json
{
  "type": "interrupt",
  "timestamp": "2026-08-18T12:00:04Z",
  "session_id": "session-123",
  "reason": "human stop"
}
```

## Other event types

`action_blocked` and `session_end` are accepted for trace completeness but do not currently add findings on their own.

## Limits

The default reader allows at most 100,000 events, 1 MB per JSONL line and 20 levels of nested action parameters. These bounds protect the local checker from accidental or hostile resource consumption.
