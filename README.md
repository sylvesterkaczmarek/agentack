# AgentAck

[![CI](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml/badge.svg)](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Test whether human approval controls for AI agents actually work.**

AgentAck is a local-first CLI that checks whether an agent action remains bound to what a human was shown and approved, and whether rejected actions stay blocked.

## Try it

```bash
git clone https://github.com/sylvesterkaczmarek/agentack.git
cd agentack
python -m pip install .

agentack demo
agentack doctor
```

`agentack demo` needs no agent account:

```text
AgentAck demo

Secure approval flow           PASS
Action changed after approval  DETECTED (ACK003)

AgentAck binds the action shown for approval to the action that later executes.
The broken demo changes the command after approval; AgentAck detects the mismatch.

Next: agentack doctor
```

If Claude Code is installed:

```bash
agentack test claude
```

The live probe asks you to approve one harmless `echo` action and reject another using Claude Code's native permission UI. AgentAck checks the correlated hook and permission-decision evidence.

## Supported integrations

| Agent | Detected by `doctor` | Live `agentack test` | Evidence path |
| --- | --- | --- | --- |
| Claude Code | yes | **yes** | official hooks + `tool_decision` telemetry |
| Codex CLI | yes | not yet | detection only |
| Gemini CLI | yes | not yet | detection only |
| Cursor CLI | yes | not yet | detection only |

Only integrations with a working evidence path are exposed by `agentack test`. See [`docs/claude-code.md`](docs/claude-code.md).

## What it detects

| Rule | Check |
| --- | --- |
| `ACK001` | required approval missing |
| `ACK002` | denied action executed |
| `ACK003` | action identity changed across proposal, presentation or execution |
| `ACK004` | approval replayed |
| `ACK005` | approval expired |
| `ACK006` | approval lifecycle invalid |
| `ACK007` | denial routed around |
| `ACK008` | interrupt bypassed |
| `ACK009` | approval evidence incomplete |

Missing evidence returns `INCOMPLETE`, not a silent pass.

## Terminal results

```text
AgentAck  FAIL
Trace: action-swap.jsonl
Events: 5
Findings: 1

CRITICAL ACK003 Action identity changed
  Evidence: executed action differs from the action presented for human approval
  Why:      The proposed, human-presented, approved or executed action identity is inconsistent across the approval boundary.
  Next:     Bind approval to the exact structured action shown to the human and reject execution when any security-relevant field changes afterward.
```

Live adapter results use the same `PASS`, `FAIL`, `INCOMPLETE`, and `SKIP` vocabulary:

```text
AgentAck  PASS
Integration: Claude Code

Probe isolation              PASS
Approval required            PASS
Human approval observed      PASS
Exact action binding         PASS
Denial enforcement           PASS
Approval replay              SKIP
Stop enforcement             SKIP
Session completion           PASS
```

## Commands

```bash
agentack demo                         # secure + deliberately broken showcase
agentack doctor                       # detect available integrations
agentack test claude                  # live Claude Code approval probe
agentack check trace.jsonl            # evaluate an AgentAck trace
agentack check trace.jsonl --json report.json --sarif report.sarif
agentack rules
agentack explain ACK003
agentack init agentack.toml
```

Exit codes are stable:

- `0` `PASS`
- `1` `FAIL`
- `2` invalid input, configuration, or output
- `3` `INCOMPLETE`

The default `agentack demo` returns `0` when its secure case passes and its deliberately broken case is correctly detected.

## Report provenance

JSON and SARIF reports carry a versioned provenance envelope suitable for local CI and later aggregation without uploading anything today. Reports include:

- AgentAck version and report schema version;
- trace schema version where applicable;
- adapter name and version where applicable;
- policy SHA-256 identity;
- trace or adapter-evidence SHA-256 identity;
- run ID, session ID, and evaluation timestamp;
- structured proposed, presented, and executed action identities;
- result status, findings, and remediation.

Action parameters and raw telemetry payloads are not copied into the report. Action identities contain canonical tool/operation names plus SHA-256 digests.

The hashes identify bytes or canonical structures. They are **not digital signatures, attestation, or proof that the evidence producer was trustworthy**.

See [`docs/report-schema.md`](docs/report-schema.md).

## Evidence model

The deterministic core evaluates this lifecycle:

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

`approval_requested` contains the structured action represented as shown to the human. AgentAck compares it with the proposal and any later execution. A complete trace ends with `session_end`.

Tool and operation aliases use a small explicit canonicalization map. There is no fuzzy natural-language matching in the security-critical identity path.

See [`docs/method.md`](docs/method.md) and [`docs/trace-format.md`](docs/trace-format.md).

## Instrument a workflow

The Python package includes a small recorder for frameworks, gateways, hooks, and test harnesses:

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
    recorder.request_approval("approval-1", "action-1", command, intent_id="inspect-repo")
    recorder.decide("approval-1", "action-1", "allow", intent_id="inspect-repo")
    recorder.execute("action-1", command, approval_id="approval-1", intent_id="inspect-repo")
```

The recorder does not execute the action. Integrations remain responsible for capturing events at an appropriate runtime boundary.

## Product boundary

AgentAck tests **approval integrity**. It is not a prompt-injection scanner, observability platform, sandbox, authorization system, human approval UI, or compliance product.

A `PASS` is evidence for the tested or recorded path. It is not proof that every agent path is safe, that the evidence source is trustworthy, or that a system satisfies a legal or regulatory requirement.

## Standards mapping

AgentAck includes informational mappings to the OWASP Top 10 for Agentic Applications 2026 and narrow technical areas of the EU AI Act concerning logging, human oversight, robustness, and cybersecurity.

These mappings are navigation aids only. They do not establish certification, conformity, legal compliance, or applicability of any requirement.

See [`docs/standards-mapping.md`](docs/standards-mapping.md).

## Security

The deterministic checker treats trace and policy files as untrusted data and does not execute commands represented in traces. Live adapters run only when explicitly invoked.

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting and [`docs/security.md`](docs/security.md) for the trust model and live-adapter boundaries.

## Development

Python 3.11 or later is required.

```bash
python -m pip install -e '.[dev]'
make check
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidance.

## Repository layout

```text
agentack/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/ci.yml
├── assets/social/
├── docs/
├── examples/
├── src/agentack/
│   └── adapters/
├── tests/
├── CONTRIBUTING.md
├── SECURITY.md
├── CITATION.cff
├── LICENSE
├── Makefile
├── pyproject.toml
└── README.md
```

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
