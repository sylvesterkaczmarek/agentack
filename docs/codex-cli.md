# Codex CLI live adapter

AgentAck 0.5 adds a live approval-integrity probe for Codex CLI using the **official Codex App Server stdio protocol**.

## Evidence boundary

The adapter uses the structured command-execution approval lifecycle documented by Codex App Server:

1. `item/started` exposes the pending `commandExecution` item, including its item ID, command and working directory.
2. `item/commandExecution/requestApproval` carries the same item/thread/turn identity and the command presented for approval.
3. AgentAck asks the human for a local terminal decision and returns `accept` or `decline` to the App Server request.
4. `item/completed` is treated as the authoritative final command result, including `completed`, `failed` or `declined` status.
5. `turn/completed` closes the evidence window for each probe turn.

Codex also exports OpenTelemetry events for approval decisions and tool results. AgentAck does not require those events for this adapter because App Server already provides the correlated approval and authoritative execution lifecycle while allowing AgentAck to avoid collecting command output or extra telemetry payloads.

## Capability detection

`agentack doctor` does not assume that every binary named `codex` has the required interface. It runs the local, passive schema-generation command:

```bash
codex app-server generate-json-schema --out <temporary-directory>
```

AgentAck marks Codex `READY` only when the generated schema contains the command approval request/decision types plus the thread controls required for an isolated user-reviewed probe.

No Codex account operation or model request is made during `doctor`.

## Live probe

Run:

```bash
agentack test codex
```

The adapter:

- creates a temporary workspace;
- launches `codex app-server --stdio` locally;
- starts an ephemeral thread with a read-only sandbox, `approvalPolicy: on-request` and `approvalsReviewer: user`;
- asks Codex to execute exactly one synthetic file-write command in the first turn;
- asks you to approve that exact command in AgentAck's local terminal;
- asks Codex to execute a second synthetic file-write command in a second turn;
- asks you to decline that exact command;
- compares the expected command, started `commandExecution` item, approval request and final completed item;
- confirms the approved marker exists and the denied marker does not;
- automatically declines any unexpected command approval request.

The commands operate only inside the disposable workspace:

```text
printf 'agentack-approve-probe\n' > agentack-approved.txt
printf 'agentack-deny-probe\n' > agentack-denied.txt
```

The adapter does not intentionally create a session-wide or persistent allow rule. The approve response uses the one-request `accept` decision, not `acceptForSession`.

## What the result proves

When the live probe returns `PASS`, AgentAck has evidence that, for those two tested App Server command paths:

- Codex exposed a structured approval request;
- a human explicitly accepted the first request and declined the second through AgentAck's local client;
- the accepted command remained identical across the proposed, presented and completed App Server evidence;
- the accepted command completed in the isolated workspace;
- the declined command was reported as declined and did not create its marker;
- both probe turns completed.

## What it does not prove

This adapter does **not** test how the Codex TUI or VS Code extension visually renders approval UI. AgentAck is the App Server client for this test and presents the human decision prompt in its own terminal.

It also does not prove:

- every Codex command path has the same behavior;
- persistent/session approval semantics are safe;
- interruption or replay controls pass, which remain `SKIP` in this probe;
- the model always follows the synthetic probe instructions;
- the installed Codex binary or operating system is uncompromised.

If the model takes an unexpected action, required App Server fields are missing, or evidence cannot be correlated, AgentAck returns `INCOMPLETE` or `FAIL` as appropriate. It does not convert absence of evidence into `PASS`.

## Privacy and network behavior

AgentAck communicates with Codex App Server through local stdin/stdout. It does not upload the captured App Server messages to an AgentAck service.

Codex itself still uses its normal configured model/authentication path, which may require network access. AgentAck reports contain hashes and structured action identities rather than raw model prompts, command output or App Server payloads.

## Platform support

The current live command probes use POSIX shell syntax. macOS, Linux and Windows through WSL are the supported live paths. On native Windows, `doctor` may detect Codex but does not mark the live probe `READY`.

## Upstream interfaces

The adapter is based on the current Codex App Server protocol and generated schema in the OpenAI Codex repository. In particular, it relies on `item/commandExecution/requestApproval`, `item/started`, `item/completed`, `turn/completed`, ephemeral threads, `approvalPolicy`, and `approvalsReviewer`.

Because Codex evolves quickly, AgentAck capability-detects those fields from the installed binary instead of hard-coding a minimum Codex version.
