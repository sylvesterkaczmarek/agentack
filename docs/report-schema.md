# Report schema

AgentAck JSON reports use a versioned envelope intended to remain useful across local CLI runs, CI systems, and future aggregation. AgentAck does not upload reports.

Current report schema version: `1`.

## Top-level structure

```json
{
  "report_schema_version": 1,
  "producer": {
    "name": "AgentAck",
    "version": "0.4.0"
  },
  "run": {
    "run_id": "UUID",
    "kind": "trace",
    "evaluated_at": "2026-08-18T16:00:00Z",
    "session_id": "session-123"
  },
  "input": {},
  "adapter": null,
  "actions": [],
  "result": {}
}
```

`kind` is `trace` for `agentack check` and `adapter` for a live adapter test.

## Input provenance

Trace reports include:

- trace schema version;
- SHA-256 of the exact input trace bytes;
- basename of the trace file, not its full local path;
- policy schema version;
- SHA-256 of the canonical policy semantics;
- basename of a supplied policy file or `default`.

Adapter reports include a SHA-256 digest of the sanitized evidence set used by the adapter when available.

These digests are identity and integrity references. They are not signatures and do not authenticate the evidence producer.

## Action identities

Each action lifecycle record can contain:

- `action_id`;
- `intent_id`;
- `approval_id`;
- decision;
- proposed/expected action identity;
- human-presented action identity;
- executed action identity;
- blocked state.

An action identity contains only:

```json
{
  "sha256": "...",
  "tool": "shell",
  "operation": "run"
}
```

Raw action parameters are intentionally excluded from report action identities. Changing a security-relevant parameter still changes the digest.

## Results

Trace results include status, event count, finding count, per-rule counts, findings, rationale, and remediation.

Live adapter results include status, individual check results, and adapter notes. Unsupported checks are reported as `SKIP` rather than implied to have passed.

## SARIF

SARIF output carries the same core run provenance through run properties. Trace findings use the `ACK001` to `ACK009` rule IDs. Live adapter checks use stable `ADAPTER_*` identifiers derived from their check labels.

## Data minimization

AgentAck does not intentionally copy raw action parameters, command output, access tokens, complete environment variables, or raw Claude telemetry payloads into JSON/SARIF reports.

Reports can still contain user-chosen identifiers such as `session_id`, `action_id`, `intent_id`, and `approval_id`. Treat reports as security evidence and store them accordingly.

## Compatibility

The report schema is versioned independently from the trace schema and the Python package version. Consumers should inspect `report_schema_version` rather than infer the schema from the AgentAck package version.

AgentAck is pre-1.0. A breaking report-envelope change requires a new `report_schema_version`.
