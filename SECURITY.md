# Security

AgentAck processes trace and policy files as untrusted input. The deterministic checker does not execute actions described by traces.

## Reporting vulnerabilities

Please use GitHub Security Advisories for vulnerabilities that could affect AgentAck users. Do not publish exploit details in a public issue before a fix is available.

Include the AgentAck version, operating system, reproduction steps, expected behavior, and observed behavior when practical. Do not include real credentials or unrelated sensitive data.

## Scope

Security-relevant areas include:

- trace/parser ambiguity or validation bypass;
- approval-rule false negatives;
- action-identity or lifecycle bypasses;
- unsafe live-adapter behavior;
- report leakage of sensitive action or telemetry data;
- local telemetry receiver vulnerabilities;
- package or CI supply-chain issues.

AgentAck is pre-1.0. Security fixes are applied to the current development line rather than maintained across multiple historical release branches.

See [`docs/security.md`](docs/security.md) for the detailed trust and adapter model.
