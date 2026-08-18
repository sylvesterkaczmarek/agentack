# Security model

AgentAck is designed to inspect evidence without executing the actions described by that evidence.

## Default safety properties

- no network calls;
- no shell execution;
- no filesystem mutation outside explicit report, policy or trace output paths selected by the user;
- bounded JSONL line size and event count;
- bounded JSON parameter nesting;
- strict schema versioning;
- duplicate JSON key rejection;
- unknown field rejection;
- deterministic action identity;
- explicit tool/operation aliasing without fuzzy matching;
- no dynamic imports from trace content;
- no pickle or executable serialization formats.

## Trust boundary

The checker trusts its own process and policy file for evaluation. It does not automatically trust the event producer.

An attacker controlling both the agent and the trace emitter could omit or fabricate proposals, human presentations, decisions or executions. Stronger deployments should place event capture at an independent action gateway, hook boundary, policy engine or execution mediator that the agent cannot rewrite.

## Human presentation evidence

AgentAck distinguishes the proposed action from the action recorded as presented to a human. It can detect inconsistencies between proposal, presentation and execution.

It cannot prove that the human actually saw, understood or approved the recorded presentation unless the integration that emits the evidence provides a trustworthy boundary for that claim.

## Action hashing

SHA-256 action identity detects differences between structured action representations after explicit canonicalization. It does not prove who created an event and is not a digital signature.

## Incomplete evidence

Missing lifecycle evidence is not converted into a successful result. AgentAck returns `INCOMPLETE` when the available trace cannot establish approval integrity and no stronger security failure is demonstrated.

## Sensitive data

Integrations should avoid placing secrets, complete environment variables, access tokens or unnecessary command output into traces. Prefer structured security-relevant metadata and redacted resource identifiers.

## Reporting vulnerabilities

Use GitHub Security Advisories for security reports. Do not publish exploit details in an issue before a fix is available.
