# Live coverage

AgentAck separates deterministic rule coverage from what each live adapter can safely establish at a real agent boundary.

Run:

```bash
agentack coverage
```

The coverage vocabulary is intentionally strict:

- **TESTED** means the path deliberately exercises the control and can produce `PASS` or `FAIL` from affirmative evidence.
- **GUARDED** means the live adapter validates the evidence boundary and fails closed on missing, malformed, or inconsistent evidence, but does not deliberately induce that attack.
- **TRACE** means the ACK rule is covered by AgentAck's deterministic trace engine, but the listed agent does not currently have a verified portable live probe for that rule.
- **SKIP** means the agent does not expose a reliable safe boundary for that live check.

Current mapping:

| Rule | Deterministic trace | Claude Code | Codex CLI | Live interpretation |
| --- | --- | --- | --- | --- |
| `ACK001` | TESTED | TESTED | TRACE | Claude baseline action crosses approval; Codex live boundary is not verified |
| `ACK002` | TESTED | TESTED | TRACE | Claude denial enforcement is exercised live |
| `ACK003` | TESTED | TESTED | TRACE | Claude exact structured action binding is exercised live |
| `ACK004` | TESTED | TESTED | TRACE | Claude one-request approval replay is exercised live |
| `ACK005` | TESTED | TRACE | TRACE | no stable portable live approval-expiry clock |
| `ACK006` | TESTED | GUARDED | TRACE | Claude malformed/truncated lifecycle fails closed |
| `ACK007` | TESTED | TESTED | TRACE | Claude denied marker intent is retried through an alternate command |
| `ACK008` | TESTED | SKIP | TRACE | Claude Stop is not a user-interrupt signal; Codex standalone boundary is not verified |
| `ACK009` | TESTED | GUARDED | TRACE | Claude missing decision/execution/session evidence returns `INCOMPLETE` |

Codex protocol fixtures and deterministic analyzers remain in the repository for research and regression testing, but they are not counted as live coverage.

A live `PASS` applies only to the synthetic paths that were actually exercised. It is not a claim that every action path in that agent is safe.
