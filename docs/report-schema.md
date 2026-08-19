# Report schema

AgentAck JSON reports use a versioned envelope intended to remain useful across local CLI runs, CI systems, and future aggregation. AgentAck does not upload reports.

Current report schema version: `1`.

## Top-level structure

```json
{
  "report_schema_version": 1,
  "producer": {
    "name": "AgentAck",
    "version": "0.6.0"
  },
  "run": {
    "run_id": "UUID",
    "kind": "trace",
    "evaluated_at": "2026-08-19T12:00:00Z",
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

Trace reports include the trace schema version, SHA-256 of the exact input trace bytes, basename of the trace file, policy schema version, SHA-256 of canonical policy semantics, and basename of a supplied policy file or `default`.

Adapter reports include a SHA-256 digest of the sanitized evidence set used by the adapter when available.

These digests are identity and integrity references. They are not signatures and do not authenticate the evidence producer.

## Action identities

Each action lifecycle record can contain `action_id`, `intent_id`, `approval_id`, decision, proposed/expected identity, human-presented identity, executed identity, and blocked state.

An action identity contains only:

```json
{
  "sha256": "...",
  "tool": "shell",
  "operation": "run"
}
```

Raw action parameters are intentionally excluded. Changing a security-relevant parameter still changes the digest.

## Results

Trace results include status, event count, finding count, per-rule counts, findings, rationale, and remediation.

Live adapter results include status, individual checks, and adapter notes. A live check can additionally include:

```json
{
  "label": "Approval replay",
  "status": "PASS",
  "detail": "...",
  "rule_id": "ACK004",
  "probe_id": "single-use-replay"
}
```

`rule_id` and `probe_id` are additive identifiers. They do not replace the ACK rule family or create a second report format. Checks that do not map directly to one ACK rule can omit them.

Unsupported checks are reported as `SKIP` rather than implied to have passed.

## SARIF

SARIF carries the same core run provenance through run properties. Trace findings use `ACK001` through `ACK009`. Live adapter SARIF remains check-oriented and uses stable `ADAPTER_*` identifiers derived from check labels; the JSON report is the richer source for optional ACK/probe identifiers.

## Data minimization

AgentAck does not intentionally copy raw action parameters, command output, access tokens, complete environment variables, or raw vendor telemetry payloads into JSON/SARIF reports.

Reports can still contain user-chosen identifiers such as `session_id`, `action_id`, `intent_id`, and `approval_id`. Treat reports as security evidence and store them accordingly.

## Compatibility

The report schema is versioned independently from the trace schema and package version. Consumers should inspect `report_schema_version` rather than infer the schema from the AgentAck version.

AgentAck is pre-1.0. A breaking report-envelope change requires a new `report_schema_version`; the optional live `rule_id` and `probe_id` fields are additive within schema version 1.
