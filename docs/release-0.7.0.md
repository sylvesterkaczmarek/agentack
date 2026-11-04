# AgentAck 0.7.0 verification

## Review outcome

The independently reviewed rc1 commit was `de94aeb7cdd0e3f23f17ad6d4fc4cf430de4c731`. The original review identified three remaining interpretation defects. The repairs address R1, R2 and R3 and include permanent regression tests.

| Finding | Repair | Control retained |
| --- | --- | --- |
| R1 contradictory/malformed telemetry | Validate typed OTLP values and alias agreement | Standard telemetry, equal aliases and identical retries |
| R2 uncorrelated attribution | Match session, tool and invocation before interpreting decisions/execution | Valid violations are preserved despite unrelated incomplete evidence |
| R3 failed execution after denial | Both terminal execution hooks violate a matched denial | Approved failed execution remains incomplete |

## Executed offline checks

Local environment: Python 3.14.7 on macOS.

- Full suite: 237 tests passed.
- Ruff and mypy: passed across all 27 runtime modules.
- Original independent semantic probes: 32/32 expected results, compared with 24/32 before repair.
- Additional malformed-input probes: 37/37 rejected with the defined input-error result and no traceback.
- Named software corpus: 20 deterministic fixtures; exact results are emitted by the verification script.

The separate review scripts were rerun unchanged. Their historical embedded commit identifies the original review; the release verification record identifies the newly tested checkout. The earlier review directories and artifacts remain preserved.

Package builds, installed-wheel validation and hosted CI are mandatory release gates. Consult the PR and Actions records for the exact released commit and final run identifiers rather than treating an earlier candidate's checks as release evidence.

## Limits

No native human approvals were automated and no paid model inference was used. Fresh supervised Claude validation remains pending. The optional Claude integration is experimental; Codex remains detection/trace-only. The release establishes the tested software behaviour and does not certify production-agent safety, complete capture authenticity or human understanding.

Reproduction commands are in [verification](verification.md); compatibility boundaries are in [migration](migration-0.7.md).
