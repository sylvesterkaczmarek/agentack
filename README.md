# AgentAck

![AgentAck](assets/social/github-social-card-agentack.png)

[![CI](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml/badge.svg)](https://github.com/sylvesterkaczmarek/agentack/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Test whether human approval controls for AI agents actually work.**

AgentAck is a local-first CLI and Python library for checking whether executed actions remain bound to human approval, whether denials are respected, and whether required evidence is complete. Its deterministic core has no third-party runtime dependencies and does not execute the actions described in a trace.

## Current development version

This branch prepares **0.7.0rc1**, an unreleased reliability update reviewed on 4 November 2026. It corrects false passes in Claude capture analysis, applies the same validation contract to files and Python callers, and separates broad policy categories from exact execution identity. The currently published PyPI release is 0.6.3 and does not contain these changes.

Use [the migration notes](docs/migration-0.7.md), [changelog](CHANGELOG.md), and [verification guide](docs/release-candidate.md) when reviewing this candidate. Fresh supervised Claude validation remains pending. Synthetic regression results are software tests, not evidence of production-agent safety or effects on human behaviour.

## Try the candidate

From this checkout:

```bash
python -m venv .venv
# Activate .venv using your operating system's normal command.
python -m pip install -e '.[dev]'
agentack demo
agentack coverage
python scripts/verify_corpus.py
```

The account-free demonstration includes a valid approval and an action changed after approval. These commands only inspect synthetic evidence.

The existing published package can still be installed with either command below. It remains 0.6.3 until a new release is explicitly approved and published:

```bash
pipx install agentack
python -m pip install agentack
```

## What it checks

| Rule | Check |
| --- | --- |
| ACK001 | required approval missing |
| ACK002 | denied action executed |
| ACK003 | proposed, presented or executed action changed |
| ACK004 | single-use approval replayed |
| ACK005 | approval expired |
| ACK006 | lifecycle ordering invalid |
| ACK007 | denial routed around through a linked intent |
| ACK008 | execution after a terminal interrupt |
| ACK009 | evidence incomplete or inconsistent |

`PASS` means the enabled checks found no violation in sufficiently complete recorded evidence. `FAIL` means a violation was demonstrated. `INCOMPLETE` means the required conclusion cannot be established. Malformed input is a separate input error.

## Commands

```bash
agentack demo
agentack demo action-swap
agentack init agentack.toml
agentack check trace.jsonl --policy agentack.toml --json report.json --sarif report.sarif
agentack rules
agentack explain ACK003
agentack doctor
agentack coverage
```

Exit codes are 0 for PASS, 1 for FAIL, 2 for invalid input/output, and 3 for INCOMPLETE. The private capture hook deliberately uses 1, never Claude's blocking hook exit code 2, for recorder errors.

[Trace format](docs/trace-format.md) and [report schema](docs/report-schema.md) describe the interfaces. JSON and SARIF reports omit raw action parameters and include versioned identity/provenance fields.

## Integrations

| Agent | Detection | Live test | Candidate status |
| --- | --- | --- | --- |
| Claude Code | yes | supervised probe | version/flag preflight plus human prompts; fresh live validation pending |
| Codex CLI | yes | no | offline protocol research and regression fixtures; no verified live boundary |
| Gemini CLI | yes | no | detection only |
| Cursor CLI | yes | no | detection only |

`agentack doctor` uses **TESTABLE** for a Claude CLI that passes local version/flag preflight. This is not a live verification result. It uses **DETECTED** for Codex and never starts an App Server turn.

A human can explicitly run the Claude probe from an interactive terminal:

```bash
agentack test claude --json claude-result.json --sarif claude-result.sarif
```

AgentAck asks the person to approve or deny four harmless commands through Claude's native prompts. It never answers them on the person's behalf. Hooks capture native tool and hashed working-directory context. Decision telemetry must match the session and tool invocation. Every probe is checked through its decision and terminal outcome; a prompt alone is insufficient.

`agentack coverage` distinguishes deterministic **TESTED** cases, implemented live **PROBE** paths, evidence **GUARDED** paths, **TRACE**-only coverage and unsupported **SKIP** paths. It is a capability map, not a claim that a particular installed version has passed.

See [Claude setup](docs/claude-code.md), [Codex limits](docs/codex-cli.md), [coverage](docs/live-coverage.md), and [dated compatibility evidence](docs/compatibility-2026-11-04.md).

## Python interface

```python
from agentack import evaluate_events
from agentack.parser import read_jsonl

report = evaluate_events(read_jsonl("trace.jsonl"))
print(report.status)
```

Direct Python calls receive the same structural validation as file inputs. Invalid input raises `TraceValidationError`, a `ValueError` subclass. `Recorder` validates events before writing. A recording can only be appended to the same unfinished session.

Broad policy aliases such as `Bash` to `shell` apply to policy matching. Identity version 2 preserves the supplied execution tool and operation instead. Different interpreters or supplied execution contexts therefore produce different hashes. A hash binds recorded data; it does not authenticate its producer or prove that an interpreter, directory or action was observed faithfully.

## Verification

```bash
make check
make release-check
python scripts/verify_wheel.py dist/agentack-0.7.0rc1-py3-none-any.whl
python scripts/showcase.py --output ./agentack-showcase
```

The suite includes named reproductions of the review findings, all 120 permutations of a five-event lifecycle, and seeded action substitutions paired with valid controls. The named corpus reports false passes, false failures and expected incomplete classifications. Every fixture is labelled synthetic.

The release workflow requires the complete CI workflow on the exact release commit before building or publishing. Release candidates cannot be published by that workflow. Merging, choosing a final version, supervised live validation and publication remain separate review decisions.

## Scope and security

AgentAck is an evidence checker, not an execution sandbox or permission-enforcement service. It cannot prove that a person saw or understood a presentation, detect an omitted action from a compromised emitter, or establish arbitrary natural-language intent equivalence. Independent capture at the execution boundary is needed for stronger deployments.

See [method](docs/method.md), [security model](docs/security.md), [standards mapping](docs/standards-mapping.md), and [security reporting](SECURITY.md).

## Cite this repository

Citation metadata is available in [CITATION.cff](CITATION.cff).

## License

MIT. See [LICENSE](LICENSE).
