# Changelog

## 0.7.0

Release prepared on 2026-11-04.

### Independent-review corrections

- R1: validate OTLP typed-value shapes and reject contradictory decision/source aliases. Retain matching aliases, valid nested metadata and identical exporter retries.
- R2: require session, tool and invocation correlation before attributing decisions or execution. Unrelated evidence remains incomplete and cannot fabricate a violation; independently established violations are retained.
- R3: treat both successful and failed tool execution after a matched rejection as ACK002. An approved tool failure remains a separate incomplete control path.
- Add 32 regression tests covering the findings and adjacent positive/negative controls. All 32 independently authored semantic probes and 37 malformed-input checks pass after repair.
- Finalize identity-2 and report-schema-2 migration guidance and public installation examples. Keep the Claude live probe experimental pending fresh supervised validation.

See [release verification](docs/release-0.7.0.md). The rc1 entry below records the earlier implementation state.

## 0.7.0rc1

Unreleased candidate prepared on 4 November 2026.

### Correctness

- Validate decision and terminal evidence for every Claude probe, including replay and alternate-route probes.
- Detect recorded execution after rejection even when a fresh prompt was shown.
- Reject success claims based on missing outcomes, wrong-session decisions, wrong-tool decisions, ambiguous identifiers or conflicting decisions.
- Validate terminal session order, capture chronology and per-invocation evidence.
- Apply shared validation to JSONL input, direct Python evaluation and recording. Reject malformed values with documented errors instead of tracebacks.
- Bound line reads, total trace/capture size and JSON nesting. Treat telemetry loss or invalid capture as incomplete.
- Keep input-error status separate from security violations.

### Identity and compatibility

- Action identity version 2 retains the supplied tool and operation. Broad aliases remain available only for policy matching.
- Claude capture version 2 binds native tool identity and a working-directory digest. Old captures cannot establish the new guarantee.
- Report schema version 2 identifies the hash semantics. Trace schema version 2 remains readable.
- Add Claude CLI capability checks and require an interactive terminal for live probes. CLI preflight does not claim live validation.
- Preserve Codex detection-only status after offline schema inspection. No model-driven Codex session was run.

### Verification and release preparation

- Add the approval-integrity-v1 synthetic corpus and generated lifecycle mutation checks with positive controls.
- Type-check the complete runtime, retain the Python/OS CI matrix, and test installed wheels.
- Gate publication on the full CI workflow for the exact release commit. Reject prerelease versions in the publication workflow.
- Add migration notes, a dated compatibility record and a reproducible offline demonstration.

No GitHub release or PyPI publication is implied by this candidate entry.

## 0.6.3

Published on 19 August 2026. The subsequent main-branch denial-authority and attribution corrections from 7 September were not included in the published 0.6.3 wheel. Version 0.7.0 includes those source changes.
