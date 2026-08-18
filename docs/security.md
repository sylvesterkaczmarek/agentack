# Security model

AgentAck is designed to inspect evidence without executing the actions described by that evidence.

## Default safety properties

- no network calls;
- no shell execution;
- no filesystem mutation outside explicit report, policy or trace output paths selected by the user;
- bounded JSONL line size and event count;
- bounded JSON parameter nesting;
- deterministic action identity;
- no dynamic imports from trace content;
- no pickle or executable serialization formats.

## Trust boundary

The checker trusts its own process and policy file for evaluation. It does not automatically trust the event producer.

An attacker controlling both the agent and the trace emitter could omit or fabricate events. Stronger deployments should place event capture at an independent action gateway, hook boundary, policy engine or execution mediator that the agent cannot rewrite.

## Action hashing

SHA-256 action identity detects a difference between the action represented by the approval and the action represented by execution. It does not prove who created either event.

A future integration can sign events or reports, but signatures would still need a trustworthy key boundary and would establish provenance rather than factual truth.

## Sensitive data

Integrations should avoid placing secrets, complete environment variables, access tokens or unnecessary command output into traces. Prefer structured security-relevant metadata and redacted resource identifiers.

## Reporting vulnerabilities

Use GitHub Security Advisories for security reports. Do not publish exploit details in an issue before a fix is available.
