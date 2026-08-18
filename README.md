# AgentAck

![AgentAck](assets/social/github-social-card-agentack.png)

[![CI](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml/badge.svg)](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

AgentAck tests whether human approval controls for AI agents actually work. The local-first CLI detects missing approvals, denied-action execution, post-approval action swaps, replay, expiry, route-around behavior and actions that continue after a human stop event.

## At a glance

```bash
pip install agentack
agentack demo secure
agentack demo action-swap
agentack check trace.jsonl --sarif agentack.sarif
```

A secure synthetic workflow passes:

```text
AgentAck  PASS
Trace: demo:secure
Events: 5
Findings: 0

No approval-integrity violations detected by the enabled rules.
```

A post-approval action swap fails:

```text
AgentAck  FAIL
Trace: demo:action-swap
Events: 3
Findings: 1

CRITICAL ACK003 Action changed after approval
         executed action hash ... differs from approved hash ...
```

## What it checks

| Rule | Check | Default severity |
| --- | --- | --- |
| `ACK001` | required approval missing | high |
| `ACK002` | denied action executed | critical |
| `ACK003` | action changed after approval | critical |
| `ACK004` | approval replayed | high |
| `ACK005` | approval expired | high |
| `ACK006` | approval ordering invalid | high |
| `ACK007` | denial routed around | critical |
| `ACK008` | interrupt bypassed | critical |
| `ACK009` | approval evidence incomplete | medium |

List or explain rules from the CLI:

```bash
agentack rules
agentack explain ACK003
```

## How it works

```mermaid
flowchart LR
    A[Agent or harness] --> B[Portable JSONL trace]
    B --> C[Canonical action identity]
    C --> D[Approval integrity rules]
    D --> E[Terminal report]
    D --> F[JSON]
    D --> G[SARIF]
    G --> H[CI security gate]
```

The checker computes a deterministic SHA-256 identity from the security-relevant action fields. An allowed approval can therefore be compared with the later execution without trusting the agent's narration about what was approved.

The CLI evaluates evidence only. It does not execute shell commands, contact network targets, delete files, mediate an approval UI or grant permissions.

## Quick start

Install from PyPI after a release exists:

```bash
pip install agentack
```

Install from source now:

```bash
git clone https://github.com/sylvesterkaczmarek/agentack.git
cd agentack
python -m pip install .
```

Run the safe deterministic examples:

```bash
agentack demo --list
agentack demo secure
agentack demo denial-bypass
agentack demo replay
agentack demo route-around
agentack demo interrupt-bypass
```

Vulnerable demo scenarios intentionally return exit code `1`.

Write a demo trace, then check it independently:

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
    recorder.request_approval("approval-1", "action-1", intent_id="inspect-repo")
    recorder.decide(
        "approval-1",
        "action-1",
        "allow",
        approved_action=command,
        intent_id="inspect-repo",
    )
    recorder.execute(
        "action-1",
        command,
        approval_id="approval-1",
        intent_id="inspect-repo",
    )
```

The recorder does not perform the action. Integrations emit evidence at their own action and approval boundaries.

See [`docs/trace-format.md`](docs/trace-format.md) for the portable event format.

## CI use

`agentack check` uses stable exit codes:

- `0` when enabled rules pass;
- `1` when one or more security findings are present;
- `2` when trace or policy input is invalid.

Generate SARIF for code-scanning systems:

```bash
agentack check trace.jsonl \
  --json agentack.json \
  --sarif agentack.sarif
```

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

Patterns use case-sensitive shell-style matching against `tool:operation`.

## Standards mapping

The rules include informational mappings to the OWASP Top 10 for Agentic Applications 2026, especially ASI09 Human-Agent Trust Exploitation, ASI02 Tool Misuse and ASI03 Identity and Privilege Abuse. Interrupt checks also relate to ASI10 Rogue Agents.

The project also identifies technical evidence that may be relevant to EU AI Act requirements for logging, effective human oversight, robustness and cybersecurity, including Articles 12, 14 and 15.

These mappings are navigation aids. A passing report is not a compliance determination or conformity assessment.

See [`docs/standards-mapping.md`](docs/standards-mapping.md).

## Security model

Trace files are treated as untrusted data. The parser bounds line size, event count and JSON nesting. The checker does not execute actions represented in a trace and does not need network access.

A valid trace can still lie. AgentAck can establish properties of the evidence it receives, but it cannot prove that the emitting adapter observed the true runtime boundary. Production assurance therefore depends on where and how trace events are captured.

See [`docs/security.md`](docs/security.md).

## What this repository does not claim

- It does not provide a human approval user interface.
- It does not enforce permissions or sandbox an agent.
- It does not prove that an adapter or trace source is trustworthy.
- It does not automatically instrument every coding agent in version `0.1.0`.
- It does not prove that an AI system complies with the EU AI Act or another standard.
- It does not establish that every harmful action requires human approval. That boundary is policy-specific.
- A passing trace is evidence for the recorded execution path, not proof about all possible paths.

## Repository layout

```text
agentack/
├── .github/workflows/ci.yml
├── assets/social/
├── docs/
├── examples/
├── src/agentack/
│   ├── canonical.py
│   ├── cli.py
│   ├── demo.py
│   ├── engine.py
│   ├── findings.py
│   ├── models.py
│   ├── parser.py
│   ├── policy.py
│   ├── recorder.py
│   └── report.py
├── tests/
├── CITATION.cff
├── LICENSE
├── Makefile
├── SECURITY.md
├── pyproject.toml
└── README.md
```

## Development

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
