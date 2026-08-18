# AgentAck

![AgentAck](assets/social/github-social-card-agentack.png)

[![CI](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml/badge.svg)](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

AgentAck tests whether human approval controls for AI agents actually work. The local-first CLI checks whether the action proposed by an agent, shown to a human, approved or denied, and ultimately executed remains consistent across the approval boundary.

## At a glance

```bash
git clone https://github.com/sylvesterkaczmarek/agentack.git
cd agentack
python -m pip install .

agentack demo secure
agentack demo action-swap
agentack check examples/secure.jsonl
```

A complete secure workflow passes:

```text
AgentAck  PASS
Trace: demo:secure
Events: 5
Findings: 0

Approval-integrity evidence is complete and no enabled rule failed.
```

An action changed after presentation fails:

```text
AgentAck  FAIL
Trace: demo:action-swap
...
CRITICAL ACK003 Action identity changed
         executed action differs from the action presented for human approval
```

A trace that lacks evidence required to establish the approval lifecycle is not treated as safe:

```text
AgentAck  INCOMPLETE
...
MEDIUM   ACK009 Approval evidence incomplete
         session_end is missing, so complete session evidence cannot be established
```

## What it checks

| Rule | Check | Default severity |
| --- | --- | --- |
| `ACK001` | required approval missing | high |
| `ACK002` | denied action executed | critical |
| `ACK003` | action identity changed across proposal, presentation or execution | critical |
| `ACK004` | approval replayed | high |
| `ACK005` | approval expired | high |
| `ACK006` | approval lifecycle invalid | high |
| `ACK007` | denial routed around | critical |
| `ACK008` | interrupt bypassed | critical |
| `ACK009` | approval evidence incomplete | medium |

```bash
agentack rules
agentack explain ACK003
```

## Evidence lifecycle

AgentAck evaluates a bounded, explicit lifecycle:

```text
ACTION PROPOSED
      |
      v
ACTION PRESENTED TO HUMAN
      |
      v
APPROVAL DECISION
      |
      +----------+
      |          |
      v          v
  EXECUTED     BLOCKED
      \          /
       v        v
       SESSION END
```

`approval_requested` records the exact structured action presented to the human. AgentAck compares that action with both the original proposal and any later execution. The approval decision therefore does not need a caller-supplied action hash.

A complete trace ends with `session_end`. Missing proposals, missing approval requests, orphan decisions and unresolved lifecycles produce `INCOMPLETE` rather than `PASS`.

See [`docs/trace-format.md`](docs/trace-format.md).

## Deterministic action identity

Security-relevant action fields are canonicalized and hashed with SHA-256. Tool and operation aliases use a small explicit map rather than fuzzy matching.

Examples that resolve to the same canonical shell action include:

```text
shell:run
Shell:RUN
Bash:exec
terminal:execute
```

Resources and parameters remain part of the action identity. Changing a command argument, file path, MCP parameter or other structured action data changes the identity.

See [`docs/method.md`](docs/method.md).

## Quick start

Run the bundled deterministic scenarios:

```bash
agentack demo --list
agentack demo secure
agentack demo denial-bypass
agentack demo replay
agentack demo route-around
agentack demo interrupt-bypass
```

Vulnerable demo scenarios intentionally return exit code `1`.

Write a demo trace and check it independently:

```bash
agentack demo secure --write trace.jsonl
agentack check trace.jsonl
```

Create a starter policy:

```bash
agentack init agentack.toml
agentack check trace.jsonl --policy agentack.toml
```

## Instrument a workflow

The package includes a small recorder for agent frameworks, hooks, gateways and test harnesses:

```python
from agentack import Action, Recorder

command = Action(
    tool="shell",
    operation="run",
    resource="workspace",
    parameters={"argv": ["git", "status"]},
)

with Recorder("trace.jsonl", "session-123") as recorder:
    recorder.propose("action-1", command, intent_id="inspect-repo")
    recorder.request_approval(
        "approval-1",
        "action-1",
        command,
        intent_id="inspect-repo",
    )
    recorder.decide(
        "approval-1",
        "action-1",
        "allow",
        intent_id="inspect-repo",
    )
    recorder.execute(
        "action-1",
        command,
        approval_id="approval-1",
        intent_id="inspect-repo",
    )
```

The recorder does not perform the action. The context manager emits `session_end` when it closes. Integrations remain responsible for capturing events at a trustworthy runtime boundary.

## Exit codes

`agentack check` and `agentack demo` use:

- `0` for `PASS`;
- `1` for `FAIL`;
- `2` for invalid input, policy or command usage;
- `3` for `INCOMPLETE` evidence.

This lets CI distinguish a demonstrated security failure from an evidence gap.

Generate machine-readable reports:

```bash
agentack check trace.jsonl \
  --json agentack.json \
  --sarif agentack.sarif
```

## Trace schema

AgentAck trace schema version `2` is strict by default:

- every JSONL event carries `"schema_version": 2`;
- duplicate JSON object keys are rejected;
- unknown event fields are rejected;
- unknown action fields are rejected;
- one trace contains exactly one `session_id`;
- line size, event count and parameter nesting are bounded.

These checks make ambiguous trace interpretation an input error rather than silently accepting data that the engine did not understand.

## Policy

The default policy requires approval for shell, write/delete filesystem, network, MCP, deployment, credential and process actions. Read-only filesystem actions are not approval-gated by default.

```toml
version = 1

[approval]
max_age_seconds = 300
single_use = true
exact_action_binding = true
stop_is_terminal = true
require_for = [
  "shell:*",
  "filesystem:write",
  "filesystem:delete",
  "network:*",
  "mcp:*",
]
```

Policy matching is performed against canonicalized `tool:operation` names.

## Standards mapping

The rules include informational mappings to the OWASP Top 10 for Agentic Applications 2026, especially ASI09 Human-Agent Trust Exploitation, ASI02 Tool Misuse and ASI03 Identity and Privilege Abuse. Interrupt checks also relate to ASI10 Rogue Agents.

The project also identifies technical evidence that may be relevant to EU AI Act requirements for logging, effective human oversight, robustness and cybersecurity, including Articles 12, 14 and 15.

These mappings are navigation aids. A passing report is not a compliance determination or conformity assessment.

See [`docs/standards-mapping.md`](docs/standards-mapping.md).

## Security model

Trace files are treated as untrusted data. The checker does not execute actions represented in a trace and does not need network access.

A syntactically valid trace can still lie. AgentAck can establish properties of the evidence it receives, but it cannot prove that the emitting adapter observed the true runtime boundary or that the recorded human presentation was authentic. Stronger deployments should capture evidence at an independent gateway, hook or execution mediator outside the agent's control.

See [`docs/security.md`](docs/security.md).

## What this repository does not claim

- It does not provide a human approval user interface.
- It does not enforce permissions or sandbox an agent.
- It does not prove that an adapter or trace source is trustworthy.
- It does not automatically instrument every coding agent in version `0.2.0`.
- It does not prove that a human actually perceived or understood the recorded presentation.
- It does not prove that an AI system complies with the EU AI Act or another standard.
- It does not establish that every harmful action requires human approval. That boundary is policy-specific.
- A `PASS` is evidence for the complete recorded execution path, not proof about all possible paths.

## Repository layout

```text
agentack/
├── .github/workflows/ci.yml
├── assets/social/
├── docs/
├── examples/
├── src/agentack/
├── tests/
├── CITATION.cff
├── LICENSE
├── Makefile
├── SECURITY.md
├── pyproject.toml
└── README.md
```

## Development

Python 3.11 or later is required.

```bash
python -m pip install -e .
make check
```

The deterministic demos use fixed timestamps and synthetic action descriptions. No demo action is executed.

## Cite this repository

If you use or adapt this repository, please cite:

> Kaczmarek, S. (2026). *AgentAck*. GitHub. https://github.com/sylvesterkaczmarek/agentack

```bibtex
@software{Kaczmarek_2026_AgentAck,
  author = {Sylvester Kaczmarek},
  title  = {{AgentAck}},
  year   = {2026},
  url    = {https://github.com/sylvesterkaczmarek/agentack}
}
```

## License

MIT. See [LICENSE](LICENSE).

© **Sylvester Kaczmarek** · [https://www.sylvesterkaczmarek.com](https://www.sylvesterkaczmarek.com)
