# Implementation verification on 4 November 2026

This record describes local implementation checks for the unpublished 0.7.0rc1 candidate. Independent review and supervised live-agent validation remain separate gates.

Base commit: `bd3c20a1fc9a7f26e8b72f02114b567db50886d9`.
Branch: `fix/approval-integrity-20261104`.
Local environment: Python 3.14.7 on macOS.

## Verification results

| Check | Result |
| --- | --- |
| Original baseline suite | 150 tests passed |
| Candidate suite | 205 tests passed |
| Ruff | Passed |
| Mypy | All 27 runtime modules passed |
| Named approval-integrity-v1 corpus | 20/20 expected classifications; zero false passes and zero false failures in this synthetic corpus |
| Generated lifecycle checks | All 120 event permutations evaluated; 100 seeded substitutions paired with 100 valid controls |
| Offline CLI checks | Passed |
| Wheel and source-distribution build | Passed |
| Twine package metadata validation | Passed |
| Clean installed-wheel verification | Complete suite, corpus and smoke passed outside the source checkout |
| Demonstration | Valid approval PASS; changed action FAIL; denied execution FAIL; missing evidence INCOMPLETE |

The named corpus and generated cases are software fixtures. They are not estimates of real-world vulnerability prevalence, human behaviour or production-agent safety.

## Main decisions

The checker now validates the entire invocation lifecycle rather than treating a permission prompt as proof of a safe outcome. Missing or ambiguous evidence remains incomplete. Explicit rejection followed by observed successful execution fails for every probe.

Shared validation applies to direct Python callers, JSONL input and recording. Input errors are distinct from security violations. Opaque session identifiers and exact execution tools are not silently merged by whitespace normalization or broad policy aliases.

Identity version 2 preserves exact supplied action fields. Claude capture version 2 binds native tool and a digest of the hook-reported working directory. Report schema 2 identifies these semantics; trace schema 2 is retained. Original traces can be re-evaluated, but absent historical context cannot be reconstructed.

CLI preflight and live validation are explicitly separate. Claude was not installed on the implementation machine. Codex 0.148.0 exposed the expected offline schema, but no model turn or approval boundary was exercised. No paid inference or native approval choices were automated.

## Reproduction

Use the commands in [candidate verification](release-candidate.md). The wheel verifier asserts that AgentAck is imported from a fresh installation, removes source-path environment overrides, and runs from a temporary directory outside the checkout.

Review [migration](migration-0.7.md) for changed hash/report semantics and [compatibility](compatibility-2026-11-04.md) for current integration limits. Hosted CI results must be checked separately against the final PR head.

No merge, final release, tag or publication follows from this implementation record.
