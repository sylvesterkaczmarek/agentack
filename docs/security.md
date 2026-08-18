# Security model

AgentAck separates its deterministic trace checker from optional live agent adapters.

## Deterministic core

`agentack check`, individual synthetic scenarios, policy parsing and report generation are designed to inspect evidence without executing the actions represented by that evidence.

Default properties of the deterministic core:

- no network access;
- no shell execution from trace content;
- no dynamic imports from trace content;
- no pickle or executable serialization formats;
- bounded JSONL line size and event count;
- bounded JSON parameter nesting;
- strict schema versioning;
- duplicate JSON key rejection;
- unknown field rejection;
- deterministic action identity;
- explicit tool/operation aliasing without fuzzy matching.

`agentack demo` evaluates synthetic in-memory actions. The synthetic actions are descriptions only and are not executed.

## Live adapters

A live adapter runs only when the user explicitly invokes `agentack test <agent>`.

The Claude Code adapter launches the installed `claude` executable in a temporary directory with a temporary settings file. The probe restricts available built-in tools to `Bash`, forces Bash through an `ask` permission rule, and asks Claude to attempt two harmless `echo` commands so the user can approve one and deny the other. Claude Code may use its normal network connection to the model provider as part of that interactive session.

AgentAck's command hooks only record sanitized event metadata. They do not return an allow/deny decision. Recorder errors deliberately avoid hook exit code `2`, because Claude Code reserves that code for blocking tool actions.

The live adapter also starts a loopback-only OTLP/HTTP JSON receiver and points the child Claude Code process at it. AgentAck uses the documented `tool_decision` event to correlate the native accept/reject decision by `tool_use_id`. Telemetry payloads remain in memory and are discarded when the test exits.

See [`claude-code.md`](claude-code.md).

## Trust boundary

The checker trusts its own process and policy file for evaluation. It does not automatically trust the event producer.

An attacker controlling both the agent and the trace emitter could omit or fabricate proposals, human presentations, decisions or executions. Stronger deployments should place event capture at an independent action gateway, hook boundary, policy engine or execution mediator that the agent cannot rewrite.

## Human presentation evidence

AgentAck distinguishes the proposed action from the action recorded as presented to a human. It can detect inconsistencies between proposal, presentation and execution.

It cannot prove that the human actually saw, understood or approved the recorded presentation unless the integration that emits the evidence provides a trustworthy boundary for that claim.

For Claude Code specifically, hooks provide the exact pre-execution and post-execution tool data while the documented OpenTelemetry `tool_decision` event provides the correlated accept/reject decision and source. AgentAck does not infer a human decision when that telemetry signal is absent.

## Action hashing

SHA-256 action identity detects differences between structured action representations after explicit canonicalization. It does not prove who created an event and is not a digital signature.

## Incomplete evidence

Missing lifecycle evidence is not converted into a successful result. AgentAck returns `INCOMPLETE` when the available trace cannot establish approval integrity and no stronger security failure is demonstrated.

Live adapters use the same principle. If a permission prompt is observed but the documented hook surface cannot establish what happened next, AgentAck reports `INCOMPLETE` rather than guessing.

## Sensitive data

Integrations should avoid placing secrets, complete environment variables, access tokens or unnecessary command output into traces. Prefer structured security-relevant metadata and redacted resource identifiers.

The built-in Claude probe stores only sanitized metadata for its synthetic command and deletes the temporary capture when the test process exits.

## Reporting vulnerabilities

Use GitHub Security Advisories for security reports. Do not publish exploit details in an issue before a fix is available.
