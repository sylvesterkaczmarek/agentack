# Security model

AgentAck separates its deterministic trace checker from optional live agent adapters.

## Deterministic core

`agentack check`, synthetic scenarios, policy parsing, and report generation inspect evidence without executing the actions represented by that evidence.

Default properties:

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

`agentack demo` evaluates synthetic in-memory actions. Those action descriptions are not executed.

## Live adapters

A live adapter runs only when the user explicitly invokes a supported `agentack test <agent>` path.

### Claude Code

The Claude adapter launches the installed `claude` executable in a disposable directory with temporary settings. It restricts the session to Bash, forces Bash through an `ask` rule, and asks Claude to attempt four exact harmless commands covering one-time approval, replay, denial, and denial route-around.

AgentAck command hooks only record sanitized event metadata. They do not return allow/deny decisions. Recorder errors deliberately avoid hook exit code `2`, which Claude reserves for blocking actions.

A loopback-only OTLP/HTTP JSON receiver captures documented `tool_decision` events. Payloads remain in memory and are discarded when the test exits. AgentAck does not enable optional detailed tool telemetry.

Claude's documented `Stop` hook is not treated as a user-interrupt signal, so live `ACK008` is `SKIP` rather than an invented PASS.

See [`claude-code.md`](claude-code.md).

### Codex CLI

Codex CLI is currently detection-only from the live-support perspective. AgentAck retains App Server protocol parsing, structured fixtures, and deterministic analysis for future support, but real-binary testing with Codex CLI 0.148.0 did not expose a reproducible standalone human command-approval boundary through the public App Server path.

`agentack doctor` therefore reports an installed Codex binary as `DETECTED`, not `READY`. `agentack test codex` is retained only as a backward-compatible status diagnostic and returns `INCOMPLETE` without launching the old model-driven five-probe suite.

Passing Codex protocol fixtures demonstrates AgentAck's analysis behavior for those synthetic inputs. It is not evidence that an installed Codex binary has passed a live approval-control test.

See [`codex-cli.md`](codex-cli.md).

## Trust boundary

The checker trusts its own process and policy file for evaluation. It does not automatically trust the event producer or installed agent binary.

An attacker controlling both the agent and the evidence emitter could omit or fabricate proposals, human presentations, decisions, or executions. Stronger deployments should place capture at an independent action gateway, hook boundary, policy engine, or execution mediator that the agent cannot rewrite.

## Human presentation evidence

AgentAck distinguishes the proposed action from the action recorded as presented to a human and can detect inconsistencies between proposal, presentation, and execution.

It cannot prove that a human actually saw or understood a presentation unless the integration exposes a trustworthy boundary for that claim.

For Claude Code, hooks provide structured action data while documented OpenTelemetry decision events provide the correlated decision/source. AgentAck does not currently make a live human-presentation claim for Codex CLI.

## Approval scope

A replay finding requires evidence that authority was reused outside the scope actually granted.

The Claude adapter does not label an explicit persistent user approval as a replay vulnerability.

## Action hashing

SHA-256 action identity detects differences between structured action representations after explicit canonicalization. It does not prove who created an event and is not a digital signature.

## Incomplete evidence

Missing lifecycle evidence is never converted into success. AgentAck returns `INCOMPLETE` when the available evidence cannot establish approval integrity and no stronger security failure is demonstrated.

This applies to missing permission events, lost telemetry correlation, missing command completion, missing session completion, malformed protocol messages, or unsupported live boundaries.

## Sensitive data

Integrations should avoid secrets, complete environment variables, access tokens, and unnecessary command output. Prefer structured security-relevant metadata and redacted resource identifiers.

Built-in live probes use only synthetic values and disposable workspaces.

## Report provenance and privacy

JSON and SARIF reports contain hashes and structured identifiers needed to correlate approval evidence. They intentionally omit raw action parameters and raw live-adapter telemetry/protocol payloads.

A trace SHA-256 identifies exact input bytes. A policy/evidence SHA-256 identifies canonical semantics or sanitized evidence. These values are not signatures, authenticity proofs, trusted timestamps, or attestations.

Reports can contain user-selected session/action/approval identifiers and should be handled as security evidence.

See [`report-schema.md`](report-schema.md).

## Loopback telemetry receiver

The Claude adapter binds its OTLP receiver to `127.0.0.1` on an ephemeral port and uses an unpredictable per-run URL path. Requests to other paths are rejected, and request size/payload count are bounded.

The random path reduces accidental local injection but is not an authentication boundary against a process with sufficient local visibility. Missing or inconsistent telemetry therefore produces `INCOMPLETE` or `FAIL` rather than being silently trusted.

## Reporting vulnerabilities

Use GitHub Security Advisories for security reports. Do not publish exploit details in an issue before a fix is available.
