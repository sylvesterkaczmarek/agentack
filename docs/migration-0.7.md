# Migration to 0.7

The 0.7 candidate changes identity and evidence semantics. Review these changes before upgrading consumers.

## Version boundaries

| Interface | Previous | Candidate |
| --- | --- | --- |
| Package | 0.6.3 | 0.7.0rc1, unpublished |
| JSONL trace | 2 | 2 |
| Action identity | unversioned alias-normalized digest | explicitly versioned identity 2 |
| JSON/SARIF report semantics | report schema 1 | report schema 2 |
| Claude capture | 1 | 2 |

## Action hashes

Identity 2 hashes canonical JSON containing `identity_version: 2` and the action object. JSON key ordering is insignificant. Supplied tool and operation identifiers, resource and parameters remain significant. Policy matching still uses the existing category aliases; exact identity never uses those aliases.

Do not compare old digests directly with identity-2 digests. Re-evaluate original traces and retain the original report alongside the new one. An old report is not silently upgraded. A version-2 trace can be read, but execution context absent from that trace cannot be reconstructed or claimed.

A generic producer should include trustworthy interpreter/context identifiers in its structured action parameters. Those values are bound by the hash but are not independently authenticated by AgentAck.

## Claude capture

The capture helper adds `_agentack_execution_context` inside the action parameters. It contains `native_tool` and `cwd_sha256`. The key is reserved and tool inputs cannot supply it. The working-directory string is hashed exactly as supplied by the hook; AgentAck does not resolve filesystem paths or read directory contents.

This digest avoids publishing the raw path. It is guessable and is not encryption or anonymisation. The native tool name is observed hook metadata, not proof of the underlying executable or filesystem state.

Legacy capture version 1 remains readable for inspection but produces INCOMPLETE when version-2 context is required. Do not fill missing context with assumed values. Fresh capture is required.

## Decisions and sessions

Every probe needs one unambiguous decision correlated by session, native tool and invocation. Byte-equivalent telemetry retries are deduplicated. Conflicting decisions are uncertain evidence; they are not arbitrarily ordered by arrival time. Known rejection followed by recorded successful execution is a violation.

An explicit persistent approval does not become a replay vulnerability. The replay check is skipped; other missing presentation or scope evidence may still leave the overall result incomplete.

## Python errors and clocks

`evaluate_events`, JSONL readers and Recorder apply the same structural contract. Empty inputs, mixed sessions, naive timestamps and malformed fields raise `TraceValidationError` (`ValueError`). Recorder validates before writing and refuses to append to an ended or different session.

Line order remains the lifecycle order. A regressing timestamp adds incomplete evidence because approval age cannot be reliably established. No claim is made to reconcile independently skewed clocks. A stronger demonstrated violation still takes precedence over an incomplete result.

CLI input errors use exit 2; demonstrated violations use exit 1; insufficient evidence uses exit 3. Capture-hook errors continue to use exit 1 to avoid changing Claude's native permission decision.
