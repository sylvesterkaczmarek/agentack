# Codex CLI status

AgentAck detects Codex CLI and retains structured App Server protocol parsing and regression fixtures, but it does **not currently advertise a verified Codex live approval-integrity test**.

## Why live support is not advertised

Real-binary testing with Codex CLI 0.148.0 repeatedly failed to produce a reproducible standalone human command-approval boundary through the public App Server path.

The public App Server protocol exposes structured command-execution approval request and lifecycle types, but a normal `turn/start` begins from user input and leaves tool invocation to the agent. In the tested standalone configuration, Codex could complete the turn without producing the `commandExecution` approval evidence AgentAck requires. Prompt retries did not make that boundary deterministic.

AgentAck therefore does not convert protocol capability or mocked fixtures into a live-support claim.

## `agentack doctor`

When Codex is installed, `agentack doctor` reports it as `DETECTED`, including the executable version when available. It does not report Codex as `READY` and does not advertise `agentack test codex` as a ready live command.

Example:

```text
Codex CLI            DETECTED   codex-cli 0.148.0
  Codex CLI is installed, but AgentAck does not currently expose a verified deterministic live approval-integrity test.
```

Detection does not start a model turn.

## `agentack test codex`

The command remains accepted for backward compatibility, but it returns a concise `INCOMPLETE` diagnostic and does not run the previous model-driven five-probe suite.

Example shape:

```text
AgentAck  INCOMPLETE
Integration: Codex CLI

Codex live approval boundary  INCOMPLETE

Details
- Codex live approval boundary: Codex CLI is installed, but AgentAck does not currently expose a verified deterministic live approval-integrity test.
```

This behavior is deliberate: AgentAck does not label a boundary as tested unless the actual installed agent reliably reaches that boundary.

## Retained protocol groundwork

The repository keeps the Codex App Server protocol parser, structured fixtures, and deterministic analysis code because they remain useful for:

- validating command approval lifecycle messages;
- exact-action correlation research;
- regression tests for replay, denial-route-around, interruption, and incomplete evidence;
- re-enabling a live adapter later if a reproducible supported public boundary becomes available.

Passing those fixtures proves the AgentAck protocol analysis logic for those synthetic inputs. It does **not** prove that a real Codex installation can be driven through the same approval boundary.

## Current coverage

`agentack coverage` reports Codex as `TRACE` for ACK001-ACK009. That means the rules remain covered by AgentAck's deterministic trace engine, not that Codex has passed a live test.

Claude Code remains the currently verified live integration.

## Re-enabling live Codex support

AgentAck should advertise Codex live support again only after a supported public Codex boundary passes a real-binary end-to-end test that can establish, with structured evidence:

1. an action requiring approval;
2. the exact action presented for approval;
3. an explicit human allow/deny decision;
4. authoritative execution or block evidence;
5. stable correlation across those events.

The test must not depend on terminal-text scraping or an undocumented private interface.

## Privacy

The current Codex status path does not launch a model turn or execute a synthetic command. Retained protocol fixtures contain only synthetic values and no credentials or real command output.

## Upstream interface

The retained parser targets the official Codex App Server JSON-RPC/JSONL lifecycle and generated schemas in the OpenAI Codex repository. Because Codex evolves quickly, future live support should be capability-detected and real-binary validated rather than enabled by a hard-coded version number.
